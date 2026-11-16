import argparse
import glob
import inspect
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time

import pandas as pd
from tqdm.auto import tqdm

MODEL_NAME = "moneysprout-26"
DEFAULT_BASE = "Qwen/Qwen2.5-3B-Instruct"   
DEFAULT_SYSTEM = (
    "You are moneysprout-26, a seasoned financial analyst assistant. "
    "You analyze financial news, judge sentiment, and forecast stock price movement."
)
SYS_RE = re.compile(r"<<SYS>>\s*(.*?)\s*<</SYS>>", re.S)
JSON_MODE = False  


def emit(**kw):
    if JSON_MODE:
        print("@@" + json.dumps(kw), flush=True)


def bar(it, **kw):
    return tqdm(it, disable=JSON_MODE, **kw)


def harden_windows(console=True):
    if os.name != "nt":
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
        k.SetThreadExecutionState(0x80000000 | 0x00000001) 
        if console:
            k.GetStdHandle.restype = ctypes.c_void_p
            k.GetStdHandle.argtypes = [ctypes.c_uint32]
            k.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            k.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            h = k.GetStdHandle(0xFFFFFFF6) 
            mode = ctypes.c_uint32()
            if h and k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080) 
    except Exception:
        pass

def split_llama2(prompt):
    """FinGPT prompts are Llama-2 style ([INST]<<SYS>>..<</SYS>>..[/INST]) -> (system, user)."""
    p = prompt.strip()
    p = re.sub(r"^\[INST\]\s*", "", p)
    p = re.sub(r"\s*\[/INST\]\s*$", "", p)
    m = SYS_RE.search(p)
    if m:
        return m.group(1).strip(), (p[: m.start()] + p[m.end():]).strip()
    return DEFAULT_SYSTEM, p


def clean(x):
    return x.strip() if isinstance(x, str) else ""


def load_records(data_dir, n_sentiment, n_headlines, n_forecaster, seed):
    rng = random.Random(seed)
    files = sorted(glob.glob(os.path.join(data_dir, "**", "*.parquet"), recursive=True))
    if not files:
        raise SystemExit(f"No .parquet files found in '{data_dir}'. Run this from the folder that contains input_data\\")

    pools = {"forecaster": {"train": [], "test": []},
             "sentiment": {"train": [], "test": []},
             "headline": {"train": [], "test": []}}

    for f in files:
        name = os.path.basename(f)
        emit(type="phase", text=f"Reading {name[:40]}")
        print(f"[load] reading {name} ...", flush=True)
        df = pd.read_parquet(f)
        cols = set(df.columns)
        split = "test" if name.lower().startswith("test") else "train"

        if {"prompt", "answer", "symbol"} <= cols:
            kind, cap = "forecaster", n_forecaster
        elif {"news", "prompt", "out"} <= cols:
            kind, cap = "sentiment", n_sentiment
        elif {"title", "text"} <= cols:
            kind, cap = "headline", n_headlines
        else:
            print(f"[skip] {f}: unrecognised columns {sorted(cols)}")
            continue
        if split == "test":
            cap = 300
        if cap and cap > 0 and len(df) > int(cap * 1.3) + 10:
            df = df.sample(n=int(cap * 1.3) + 10, random_state=seed).reset_index(drop=True)

        recs = []
        desc = name[:28]
        if kind == "forecaster":
            for p, a in bar(zip(df["prompt"], df["answer"]), total=len(df), desc=desc, leave=False):
                p, a = clean(p), clean(a)
                if p and a:
                    s, u = split_llama2(p)
                    recs.append({"system": s, "user": u, "answer": a})
        elif kind == "sentiment":
            for p, a in bar(zip(df["prompt"], df["out"]), total=len(df), desc=desc, leave=False):
                p, a = clean(p), clean(a)
                if p and a:
                    recs.append({"system": DEFAULT_SYSTEM, "user": p, "answer": a})
        else:
            for t, x in bar(zip(df["title"], df["text"]), total=len(df), desc=desc, leave=False):
                t, x = clean(t), clean(x)
                if len(t) >= 10 and len(x) >= 200:
                    recs.append({"system": DEFAULT_SYSTEM,
                                 "user": "Write a headline for this financial news article:\n\n" + x[:2000],
                                 "answer": t})
        print(f"[load] {name} -> {kind}/{split}: {len(recs)} usable rows", flush=True)
        pools[kind][split].extend(recs)
        del df

    def take(lst, n):
        if n and n > 0 and len(lst) > n:
            return rng.sample(lst, n)
        return list(lst)

    train = (take(pools["forecaster"]["train"], n_forecaster)
             + take(pools["sentiment"]["train"], n_sentiment)
             + take(pools["headline"]["train"], n_headlines))
    return train, pools


def encode(rec, tok, max_len):
    """Tokenize one example; loss only on the answer. Over-long prompts are trimmed in the middle."""
    ans_ids = tok(rec["answer"] + tok.eos_token, add_special_tokens=False)["input_ids"]
    budget = max_len - len(ans_ids)
    if budget < 256:
        return None

    def build(user):
        msgs = [{"role": "system", "content": rec["system"]}, {"role": "user", "content": user}]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        return tok(text, add_special_tokens=False)["input_ids"]

    user = rec["user"]
    prompt_ids = build(user)
    tries = 0
    while len(prompt_ids) > budget:
        tries += 1
        if tries > 6:
            return None
        user_ids = tok(user, add_special_tokens=False)["input_ids"]
        keep = len(user_ids) - (len(prompt_ids) - budget) - 16 * tries
        if keep < 200:
            return None
        head = int(keep * 0.4)
        tail = keep - head
        user = tok.decode(user_ids[:head]) + "\n...\n" + tok.decode(user_ids[-tail:])
        prompt_ids = build(user)

    input_ids = prompt_ids + ans_ids
    labels = [-100] * len(prompt_ids) + ans_ids
    return {"input_ids": input_ids, "attention_mask": [1] * len(input_ids), "labels": labels}


class ListDataset:
    def __init__(self, items):
        self.items = items

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def build_dataset(recs, tok, max_len, name):
    out, dropped, total = [], 0, len(recs)
    for i, r in enumerate(bar(recs, desc=f"tokenizing {name}")):
        e = encode(r, tok, max_len)
        if e is None:
            dropped += 1
        else:
            out.append(e)
        if JSON_MODE and i % 250 == 0:
            emit(type="phase", text=f"Tokenizing {name}", done=i, total=total)
    print(f"[data] {name}: {len(out)} examples ({dropped} dropped as too long)", flush=True)
    return ListDataset(out)


def grouped_order(lengths, batch_size, seed, epoch):
    """Speed: shuffle, then sort by length inside chunks so each batch has similar-length examples
    (almost no padding waste), then shuffle the batches. Returns a list of dataset indices."""
    rnd = random.Random(seed + epoch)
    idx = list(range(len(lengths)))
    rnd.shuffle(idx)
    bs = max(1, batch_size)
    chunk = bs * 64
    batches = []
    for i in range(0, len(idx), chunk):
        c = sorted(idx[i:i + chunk], key=lambda j: -lengths[j])
        batches.extend(c[k:k + bs] for k in range(0, len(c), bs))
    rnd.shuffle(batches)
    return [j for b in batches for j in b]

def check_cuda():
    import torch
    print(f"[env] torch {torch.__version__} | built for CUDA: {torch.version.cuda} | GPU available: {torch.cuda.is_available()}", flush=True)
    if torch.cuda.is_available():
        print(f"[env] GPU: {torch.cuda.get_device_name(0)}", flush=True)
        return
    if torch.version.cuda is None:
        raise SystemExit(
            "\nPyTorch here is the CPU-only build (pip's default on Windows). Fix:\n"
            "  pip uninstall -y torch torchvision torchaudio\n"
            "  pip install torch --index-url https://download.pytorch.org/whl/cu124\n"
            "Then verify: python -c \"import torch; print(torch.cuda.is_available())\" -> True")
    raise SystemExit(
        "\nPyTorch has CUDA support but can't see the GPU. Run `nvidia-smi` in PowerShell; if it fails, "
        "install/update the NVIDIA driver and reboot. Also make sure you're using the same Python/venv "
        "you installed torch into.")


def load_tokenizer(path):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(path)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"
    return tok


def load_4bit(base):
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    return AutoModelForCausalLM.from_pretrained(base, quantization_config=bnb,
                                                device_map={"": 0}, torch_dtype=torch.bfloat16)


def read_base(adapter, fallback):
    p = os.path.join(adapter, "base_model.txt")
    return open(p).read().strip() if os.path.exists(p) else fallback


def generate(model, tok, user, max_new_tokens):
    import torch
    msgs = [{"role": "system", "content": DEFAULT_SYSTEM}, {"role": "user", "content": user}]
    ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                  return_dict=True).to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.pad_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def cmd_train(a):
    import torch
    from torch.utils.data import Sampler
    check_cuda()
    emit(type="phase", text="Loading libraries")
    print("[env] loading peft/transformers/bitsandbytes (a 'Failed to find CUDA' warning is harmless) ...", flush=True)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import DataCollatorForSeq2Seq, Trainer, TrainerCallback, TrainingArguments, set_seed

    harden_windows()
    if not torch.cuda.is_bf16_supported():
        raise SystemExit("This GPU does not support bf16; edit the script to use fp16.")
    torch.backends.cuda.matmul.allow_tf32 = True
    set_seed(a.seed)

    os.makedirs(a.out, exist_ok=True)
    stop_file = os.path.join(a.out, "STOP")
    if os.path.exists(stop_file):
        os.remove(stop_file)

    train_recs, pools = load_records(a.data, a.n_sentiment, a.n_headlines, a.n_forecaster, a.seed)
    rng = random.Random(a.seed + 1)
    eval_recs = pools["forecaster"]["test"] + pools["sentiment"]["test"]
    if len(eval_recs) > a.eval_size:
        eval_recs = rng.sample(eval_recs, a.eval_size)
    rng.shuffle(train_recs)
    print(f"[data] train records: {len(train_recs)} | eval records: {len(eval_recs)}", flush=True)

    tok = load_tokenizer(a.base)
    train_ds = build_dataset(train_recs, tok, a.max_len, "train")
    eval_ds = build_dataset(eval_recs, tok, a.max_len, "eval") if eval_recs else None
    if len(train_ds) == 0:
        raise SystemExit("No training examples after filtering.")

    emit(type="phase", text="Loading base model (first run downloads it, can take a few minutes)")
    print(f"[model] loading {a.base} in 4-bit ...", flush=True)
    model = load_4bit(a.base)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                            gradient_checkpointing_kwargs={"use_reentrant": False})
    lora = LoraConfig(r=a.lora_r, lora_alpha=a.lora_r * 2, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lora)
    model.config.use_cache = False
    model.print_trainable_parameters()

    class LengthGroupedSampler(Sampler):
        def __init__(self, lengths, batch_size, seed):
            self.lengths, self.bs, self.seed, self.epoch = lengths, batch_size, seed, 0

        def __len__(self):
            return len(self.lengths)

        def __iter__(self):
            order = grouped_order(self.lengths, self.bs, self.seed, self.epoch)
            self.epoch += 1
            return iter(order)

    class SproutTrainer(Trainer):
        def _get_train_sampler(self, *args, **kwargs):
            lengths = [len(x["input_ids"]) for x in self.train_dataset.items]
            return LengthGroupedSampler(lengths, self.args.per_device_train_batch_size, self.args.seed)

    class ProgressCallback(TrainerCallback):
        """Live progress for the UI, plus 'Stop & save' (STOP file) and an optional time limit."""
        def on_train_begin(self, args, state, control, **kw):
            self.t0, self.s0 = time.time(), state.global_step
            emit(type="train_begin", max=state.max_steps)

        def on_step_end(self, args, state, control, **kw):
            el = time.time() - self.t0
            done = max(1, state.global_step - self.s0)
            eta = el / done * max(0, state.max_steps - state.global_step)
            emit(type="step", step=state.global_step, max=state.max_steps, elapsed=el, eta=eta)
            if os.path.exists(stop_file):
                print("[train] stop requested - saving adapter ...", flush=True)
                control.should_training_stop = True
            elif a.max_minutes and el > a.max_minutes * 60:
                print(f"[train] {a.max_minutes} minute limit reached - saving adapter ...", flush=True)
                control.should_training_stop = True
            return control

        def on_log(self, args, state, control, logs=None, **kw):
            logs = logs or {}
            if "eval_loss" in logs:
                emit(type="eval", step=state.global_step, eval_loss=logs["eval_loss"])
            elif "loss" in logs:
                emit(type="loss", step=state.global_step, loss=logs["loss"])

    kwargs = dict(
        output_dir=os.path.join(a.out, "checkpoints"),
        num_train_epochs=a.epochs,
        max_steps=a.max_steps,
        per_device_train_batch_size=a.batch_size,
        per_device_eval_batch_size=a.batch_size,
        gradient_accumulation_steps=a.grad_accum,
        learning_rate=a.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        max_grad_norm=0.3,
        bf16=True,
        optim="paged_adamw_8bit",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=5,
        logging_first_step=True,
        disable_tqdm=JSON_MODE,
        save_strategy="steps",
        save_steps=a.save_steps,
        save_total_limit=2,
        eval_steps=a.eval_every,
        report_to="none",
        dataloader_num_workers=0,
        remove_unused_columns=False,
    )
    
    params = inspect.signature(TrainingArguments.__init__).parameters
    eval_key = "eval_strategy" if "eval_strategy" in params else "evaluation_strategy"
    kwargs[eval_key] = "steps" if eval_ds else "no"
    args = TrainingArguments(**kwargs)

    trainer = SproutTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=eval_ds,
                            data_collator=DataCollatorForSeq2Seq(tok, padding=True, pad_to_multiple_of=8,
                                                                 label_pad_token_id=-100),
                            callbacks=[ProgressCallback()])

    ckpt_dir = os.path.join(a.out, "checkpoints")
    resume = a.resume and os.path.isdir(ckpt_dir) and any(d.startswith("checkpoint-") for d in os.listdir(ckpt_dir))
    trainer.train(resume_from_checkpoint=True if resume else None)

    emit(type="phase", text="Saving adapter")
    final = os.path.join(a.out, "adapter")
    trainer.save_model(final)
    tok.save_pretrained(final)
    with open(os.path.join(final, "base_model.txt"), "w") as f:
        f.write(a.base)
    if os.path.exists(stop_file):
        os.remove(stop_file)
    emit(type="done", path=os.path.abspath(final))
    print(f"\n[done] {MODEL_NAME} adapter saved to: {final}", flush=True)
    print("       chat with it:  python train_moneysprout.py   (Chat tab)", flush=True)

def cmd_chat(a):
    import torch  
    check_cuda()
    from peft import PeftModel
    adapter = os.path.join(a.out, "adapter")
    base = read_base(adapter, a.base)
    tok = load_tokenizer(adapter)
    model = PeftModel.from_pretrained(load_4bit(base), adapter)
    model.eval()
    print(f"{MODEL_NAME} ready. Paste a news headline/question (blank line to quit).")
    while True:
        try:
            user = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user:
            break
        print("\n" + MODEL_NAME + "> " + generate(model, tok, user, a.max_new_tokens))


def cmd_serve(a):
    """Used by the UI's Chat tab: reads one JSON request per stdin line, answers with @@ JSON lines."""
    import torch 
    check_cuda()
    from peft import PeftModel
    adapter = os.path.join(a.out, "adapter")
    if not os.path.isdir(adapter):
        emit(type="error", text=f"No trained adapter found at {adapter}. Train first.")
        raise SystemExit(1)
    emit(type="phase", text="Loading model")
    base = read_base(adapter, a.base)
    tok = load_tokenizer(adapter)
    model = PeftModel.from_pretrained(load_4bit(base), adapter)
    model.eval()
    emit(type="ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            emit(type="reply", text=generate(model, tok, req["prompt"], int(req.get("max_new_tokens", 300))))
        except Exception as e: 
            emit(type="error", text=repr(e))


def cmd_merge(a):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM
    adapter = os.path.join(a.out, "adapter")
    base = read_base(adapter, a.base)
    model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16, device_map="cpu")
    model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    dest = os.path.join(a.out, "merged")
    model.save_pretrained(dest, safe_serialization=True)
    load_tokenizer(adapter).save_pretrained(dest)
    print(f"[done] merged {MODEL_NAME} saved to: {dest}")

def fmt_time(sec):
    sec = int(max(0, sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}"


PRESETS = {
    "Smoke test (verify everything works)": dict(max_len=1024, epochs=1, nf=20, ns=20, nh=20, bs=2, ga=2, minutes=0, max_steps=4),
    "Fast": dict(max_len=1536, epochs=1, nf=0, ns=2000, nh=1000, bs=2, ga=8, minutes=0, max_steps=-1),
    "Balanced": dict(max_len=1536, epochs=1, nf=0, ns=6000, nh=3000, bs=2, ga=8, minutes=0, max_steps=-1),
    "Full (long!)": dict(max_len=2048, epochs=1, nf=0, ns=0, nh=15000, bs=2, ga=8, minutes=0, max_steps=-1),
}
BASES = ["Qwen/Qwen2.5-1.5B-Instruct", "Qwen/Qwen2.5-3B-Instruct", "Qwen/Qwen2.5-7B-Instruct"]
NO_WINDOW = 0x08000000
ABOVE_NORMAL = 0x00008000


def cmd_ui(a):
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    harden_windows(console=False)
    script = os.path.abspath(__file__)

    class App:
        FIELDS = [("Max length (tokens)", "max_len"), ("Epochs", "epochs"),
                  ("Forecaster examples (0=all)", "nf"), ("Sentiment examples (0=all)", "ns"),
                  ("Headline examples", "nh"), ("Batch size", "bs"),
                  ("Grad accumulation", "ga"), ("Time limit, min (0=none)", "minutes"),
                  ("Max steps (-1=off)", "max_steps")]

        def __init__(self, root):
            self.root = root
            root.title(f"{MODEL_NAME} trainer")
            root.geometry("1000x820")
            self.q = queue.Queue()
            self.proc = None
            self.chat_proc = None
            self.chat_ready = False
            self.chat_busy = False
            self.losses = []
            self.gpu_busy = False
            self.v = {k: tk.StringVar() for k in
                      ["base", "max_len", "epochs", "nf", "ns", "nh", "bs", "ga", "minutes", "max_steps", "data", "out"]}
            self.resume = tk.BooleanVar(value=False)
            nb = ttk.Notebook(root)
            nb.pack(fill="both", expand=True)
            self.train_tab, self.chat_tab = ttk.Frame(nb), ttk.Frame(nb)
            nb.add(self.train_tab, text="  Train  ")
            nb.add(self.chat_tab, text="  Chat  ")
            self.build_train()
            self.build_chat()
            self.v["base"].set(DEFAULT_BASE)
            self.v["data"].set(a.data)
            self.v["out"].set(a.out)
            self.apply_preset("Balanced")
            self.preset_box.set("Balanced")
            root.after(100, self.poll)
            root.after(500, self.poll_gpu)
            root.protocol("WM_DELETE_WINDOW", self.on_close)

        def build_train(self):
            t = self.train_tab
            top = ttk.LabelFrame(t, text="Settings")
            top.pack(fill="x", padx=10, pady=(10, 4))
            ttk.Label(top, text="Preset").grid(row=0, column=0, sticky="w", padx=6, pady=4)
            self.preset_box = ttk.Combobox(top, values=list(PRESETS), state="readonly", width=38)
            self.preset_box.grid(row=0, column=1, columnspan=3, sticky="w", pady=4)
            self.preset_box.bind("<<ComboboxSelected>>", lambda e: self.apply_preset(self.preset_box.get()))
            ttk.Label(top, text="Base model").grid(row=1, column=0, sticky="w", padx=6, pady=4)
            ttk.Combobox(top, values=BASES, textvariable=self.v["base"], width=38).grid(
                row=1, column=1, columnspan=3, sticky="w", pady=4)
            for i, (lab, key) in enumerate(self.FIELDS):
                r, c = divmod(i, 2)
                ttk.Label(top, text=lab).grid(row=2 + r, column=c * 2, sticky="w", padx=6, pady=3)
                ttk.Entry(top, textvariable=self.v[key], width=14).grid(row=2 + r, column=c * 2 + 1, sticky="w", pady=3)
            base_row = 2 + (len(self.FIELDS) + 1) // 2
            ttk.Label(top, text="Data folder").grid(row=base_row, column=0, sticky="w", padx=6, pady=3)
            ttk.Entry(top, textvariable=self.v["data"], width=40).grid(row=base_row, column=1, columnspan=2, sticky="w")
            ttk.Button(top, text="Browse", command=lambda: self.browse("data")).grid(row=base_row, column=3, sticky="w")
            ttk.Label(top, text="Output folder").grid(row=base_row + 1, column=0, sticky="w", padx=6, pady=3)
            ttk.Entry(top, textvariable=self.v["out"], width=40).grid(row=base_row + 1, column=1, columnspan=2, sticky="w")
            ttk.Button(top, text="Browse", command=lambda: self.browse("out")).grid(row=base_row + 1, column=3, sticky="w")

            btns = ttk.Frame(t)
            btns.pack(fill="x", padx=10, pady=6)
            self.start_btn = ttk.Button(btns, text="Start training", command=self.start)
            self.start_btn.pack(side="left")
            self.stop_btn = ttk.Button(btns, text="Stop & save", command=self.stop_save, state="disabled")
            self.stop_btn.pack(side="left", padx=6)
            self.kill_btn = ttk.Button(btns, text="Force quit", command=self.force_quit, state="disabled")
            self.kill_btn.pack(side="left")
            ttk.Checkbutton(btns, text="Resume from last checkpoint", variable=self.resume).pack(side="left", padx=14)

            st = ttk.LabelFrame(t, text="Progress")
            st.pack(fill="x", padx=10, pady=4)
            self.status = tk.StringVar(value="Idle")
            ttk.Label(st, textvariable=self.status, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
            self.pbar = ttk.Progressbar(st, mode="determinate", maximum=100)
            self.pbar.pack(fill="x", padx=8, pady=2)
            self.info = tk.StringVar(value="")
            ttk.Label(st, textvariable=self.info).pack(anchor="w", padx=8)
            self.gpu = tk.StringVar(value="GPU: ...")
            ttk.Label(st, textvariable=self.gpu, foreground="#555").pack(anchor="w", padx=8, pady=(0, 6))

            self.canvas = tk.Canvas(t, height=130, bg="white", highlightthickness=1, highlightbackground="#bbb")
            self.canvas.pack(fill="x", padx=10, pady=4)
            self.draw_loss()
            self.log = scrolledtext.ScrolledText(t, height=12, state="disabled", font=("Consolas", 9))
            self.log.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        def apply_preset(self, name):
            for k, val in PRESETS[name].items():
                self.v[k].set(str(val))

        def browse(self, key):
            d = filedialog.askdirectory(initialdir=self.v[key].get() or ".")
            if d:
                self.v[key].set(d)

        def log_line(self, text):
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            if int(self.log.index("end-1c").split(".")[0]) > 3000:
                self.log.delete("1.0", "500.0")
            self.log.see("end")
            self.log.configure(state="disabled")

        def set_progress(self, frac):
            if frac is None:
                self.pbar.configure(mode="indeterminate")
                self.pbar.start(15)
            else:
                self.pbar.stop()
                self.pbar.configure(mode="determinate", value=max(0, min(100, frac * 100)))

        def running(self):
            return self.proc is not None and self.proc.poll() is None

        def spawn(self, cmd, tag, stdin=False):
            env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                       HF_HUB_DISABLE_PROGRESS_BARS="1", TOKENIZERS_PARALLELISM="false")
            flags = (NO_WINDOW | ABOVE_NORMAL) if os.name == "nt" else 0
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                    env=env, cwd=os.getcwd(), creationflags=flags)

            def reader():
                for raw in iter(proc.stdout.readline, b""):
                    self.q.put((tag, raw.decode("utf-8", "replace").rstrip()))
                proc.wait()
                self.q.put((tag + "_exit", proc.returncode))

            threading.Thread(target=reader, daemon=True).start()
            return proc

        def start(self):
            if self.running():
                return
            if self.chat_proc and self.chat_proc.poll() is None:
                if not messagebox.askyesno("Chat model loaded", "The chat model is using GPU memory. Close it and start training?"):
                    return
                self.stop_chat()
            try:
                vals = {"max_len": int(self.v["max_len"].get()), "epochs": float(self.v["epochs"].get()),
                        "nf": int(self.v["nf"].get()), "ns": int(self.v["ns"].get()), "nh": int(self.v["nh"].get()),
                        "bs": int(self.v["bs"].get()), "ga": int(self.v["ga"].get()),
                        "minutes": float(self.v["minutes"].get()), "max_steps": int(self.v["max_steps"].get())}
            except ValueError:
                messagebox.showerror("Bad setting", "One of the number fields isn't a valid number.")
                return
            data, out = self.v["data"].get().strip(), self.v["out"].get().strip()
            if not os.path.isdir(data):
                messagebox.showerror("Data folder", f"Folder not found:\n{data}")
                return
            os.makedirs(out, exist_ok=True)
            stop = os.path.join(out, "STOP")
            if os.path.exists(stop):
                os.remove(stop)
            cmd = [sys.executable, "-u", script, "train", "--json-progress",
                   "--base", self.v["base"].get().strip(), "--data", data, "--out", out,
                   "--max-len", str(vals["max_len"]), "--epochs", str(vals["epochs"]),
                   "--n-forecaster", str(vals["nf"]), "--n-sentiment", str(vals["ns"]),
                   "--n-headlines", str(vals["nh"]), "--batch-size", str(vals["bs"]),
                   "--grad-accum", str(vals["ga"]), "--max-minutes", str(vals["minutes"]),
                   "--max-steps", str(vals["max_steps"])]
            if self.resume.get():
                cmd.append("--resume")
            self.losses = []
            self.draw_loss()
            self.log_line("$ " + " ".join(cmd[2:]))
            self.proc = self.spawn(cmd, "train")
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.kill_btn.configure(state="normal")
            self.status.set("Starting...")
            self.info.set("")
            self.set_progress(None)

        def stop_save(self):
            out = self.v["out"].get().strip()
            try:
                os.makedirs(out, exist_ok=True)
                open(os.path.join(out, "STOP"), "w").close()
                self.status.set("Stopping after the current step, then saving the adapter...")
                self.log_line("[ui] stop requested (only works once training steps have started; use Force quit during loading)")
            except OSError as e:
                self.log_line(f"[ui] couldn't write STOP file: {e}")

        def force_quit(self):
            if self.running():
                self.proc.terminate()
                self.log_line("[ui] training process terminated")

        def build_chat(self):
            t = self.chat_tab
            top = ttk.Frame(t)
            top.pack(fill="x", padx=10, pady=10)
            self.load_btn = ttk.Button(top, text="Load trained model", command=self.load_chat)
            self.load_btn.pack(side="left")
            self.unload_btn = ttk.Button(top, text="Unload", command=self.stop_chat, state="disabled")
            self.unload_btn.pack(side="left", padx=6)
            self.chat_status = tk.StringVar(value="Model not loaded (train first, and don't train while it is loaded)")
            ttk.Label(top, textvariable=self.chat_status).pack(side="left", padx=10)
            self.chat_out = scrolledtext.ScrolledText(t, state="disabled", wrap="word", font=("Segoe UI", 10))
            self.chat_out.pack(fill="both", expand=True, padx=10, pady=4)
            mid = ttk.Frame(t)
            mid.pack(fill="x", padx=10)
            ttk.Label(mid, text="Mode:").pack(side="left")
            self.chat_mode = ttk.Combobox(mid, values=["Free chat", "Sentiment of news", "Write a headline"],
                                          state="readonly", width=20)
            self.chat_mode.set("Sentiment of news")
            self.chat_mode.pack(side="left", padx=6)
            self.chat_in = tk.Text(t, height=5, wrap="word", font=("Segoe UI", 10))
            self.chat_in.pack(fill="x", padx=10, pady=6)
            self.chat_in.bind("<Control-Return>", lambda e: (self.send_chat(), "break")[1])
            self.send_btn = ttk.Button(t, text="Send (Ctrl+Enter)", command=self.send_chat, state="disabled")
            self.send_btn.pack(anchor="e", padx=10, pady=(0, 10))

        def chat_print(self, text):
            self.chat_out.configure(state="normal")
            self.chat_out.insert("end", text + "\n\n")
            self.chat_out.see("end")
            self.chat_out.configure(state="disabled")

        def load_chat(self):
            if self.running():
                messagebox.showinfo("Training is running", "Stop training first - both need the GPU memory.")
                return
            if self.chat_proc and self.chat_proc.poll() is None:
                return
            out = self.v["out"].get().strip()
            if not os.path.isdir(os.path.join(out, "adapter")):
                messagebox.showinfo("No model yet", "No trained adapter found. Run training first.")
                return
            self.chat_ready = False
            self.chat_status.set("Loading model...")
            self.load_btn.configure(state="disabled")
            self.chat_proc = self.spawn([sys.executable, "-u", script, "serve", "--out", out,
                                         "--base", self.v["base"].get().strip()], "chat", stdin=True)

        def stop_chat(self):
            if self.chat_proc and self.chat_proc.poll() is None:
                self.chat_proc.terminate()
            self.chat_ready = False
            self.chat_status.set("Model not loaded")
            self.load_btn.configure(state="normal")
            self.unload_btn.configure(state="disabled")
            self.send_btn.configure(state="disabled")

        def send_chat(self):
            if not self.chat_ready or self.chat_busy:
                return
            text = self.chat_in.get("1.0", "end").strip()
            if not text:
                return
            mode = self.chat_mode.get()
            if mode == "Sentiment of news":
                prompt = ("What is the sentiment of this news?\n" + text + "\nPlease choose an answer from "
                          "{strong negative/moderately negative/mildly negative/neutral/mildly positive/"
                          "moderately positive/strong positive}, then provide some short reasons.")
            elif mode == "Write a headline":
                prompt = "Write a headline for this financial news article:\n\n" + text
            else:
                prompt = text
            self.chat_print("YOU: " + text)
            self.chat_in.delete("1.0", "end")
            try:
                self.chat_proc.stdin.write((json.dumps({"prompt": prompt, "max_new_tokens": 400}) + "\n").encode("utf-8"))
                self.chat_proc.stdin.flush()
            except OSError:
                self.chat_print("[model process is not running - reload the model]")
                return
            self.chat_busy = True
            self.send_btn.configure(state="disabled")
            self.chat_status.set("Thinking...")

        def draw_loss(self):
            c = self.canvas
            c.delete("all")
            w, h = max(c.winfo_width(), 400), int(c["height"])
            pts = self.losses
            if len(pts) < 2:
                c.create_text(w / 2, h / 2, text="loss chart appears once training starts", fill="#888")
                return
            lo, hi = min(l for _, l in pts), max(l for _, l in pts)
            span = (hi - lo) or 1.0
            x0, x1, y0, y1 = 48, w - 12, 12, h - 20
            smin, smax = pts[0][0], pts[-1][0]
            sspan = (smax - smin) or 1
            coords = []
            for s, l in pts:
                coords += [x0 + (s - smin) / sspan * (x1 - x0), y1 - (l - lo) / span * (y1 - y0)]
            c.create_line(x0, y0, x0, y1, x1, y1, fill="#999")
            c.create_line(*coords, fill="#2a7ae2", width=2)
            c.create_text(4, y0, text=f"{hi:.2f}", anchor="w", fill="#555")
            c.create_text(4, y1, text=f"{lo:.2f}", anchor="w", fill="#555")
            c.create_text(x1, h - 8, text=f"step {smax}", anchor="e", fill="#555")

        def handle_train(self, line):
            if line.startswith("@@"):
                try:
                    m = json.loads(line[2:])
                except ValueError:
                    return
                kind = m.get("type")
                if kind == "phase":
                    text = m.get("text", "")
                    if m.get("total"):
                        self.status.set(f"{text}  ({m['done']}/{m['total']})")
                        self.set_progress(m["done"] / max(1, m["total"]))
                    else:
                        self.status.set(text + " ...")
                        self.set_progress(None)
                elif kind == "train_begin":
                    self.status.set("Training")
                    self.set_progress(0)
                elif kind == "step":
                    mx = max(1, m["max"])
                    self.set_progress(m["step"] / mx)
                    self.status.set(f"Training  -  step {m['step']}/{mx}")
                    self.info.set(f"elapsed {fmt_time(m['elapsed'])}   |   ETA {fmt_time(m['eta'])}"
                                  + (f"   |   loss {self.losses[-1][1]:.4f}" if self.losses else ""))
                elif kind == "loss":
                    self.losses.append((m["step"], float(m["loss"])))
                    self.draw_loss()
                elif kind == "eval":
                    self.log_line(f"[eval] step {m['step']}: eval_loss = {m['eval_loss']:.4f}")
                elif kind == "done":
                    self.status.set("Done - adapter saved")
                    self.set_progress(1)
                    self.log_line(f"[done] adapter saved to {m['path']}")
                return
            line = line.split("\r")[-1]
            if line.strip():
                self.log_line(line)

        def handle_chat(self, line):
            if not line.startswith("@@"):
                if line.strip():
                    self.log_line("[chat] " + line.split("\r")[-1])
                return
            try:
                m = json.loads(line[2:])
            except ValueError:
                return
            kind = m.get("type")
            if kind == "ready":
                self.chat_ready, self.chat_busy = True, False
                self.chat_status.set("Model ready")
                self.unload_btn.configure(state="normal")
                self.send_btn.configure(state="normal")
            elif kind == "reply":
                self.chat_print(f"{MODEL_NAME}: " + m["text"])
                self.chat_busy = False
                self.chat_status.set("Model ready")
                self.send_btn.configure(state="normal")
            elif kind == "error":
                self.chat_print("[error] " + m.get("text", ""))
                self.chat_busy = False
                if self.chat_ready:
                    self.send_btn.configure(state="normal")
            elif kind == "phase":
                self.chat_status.set(m.get("text", "") + " ...")

        def poll(self):
            try:
                for _ in range(300):
                    item = self.q.get_nowait()
                    tag = item[0]
                    if tag == "train":
                        self.handle_train(item[1])
                    elif tag == "chat":
                        self.handle_chat(item[1])
                    elif tag == "gpu":
                        self.gpu.set(item[1])
                    elif tag == "train_exit":
                        code = item[1]
                        self.start_btn.configure(state="normal")
                        self.stop_btn.configure(state="disabled")
                        self.kill_btn.configure(state="disabled")
                        self.pbar.stop()
                        if code == 0:
                            if not self.status.get().startswith("Done"):
                                self.status.set("Finished")
                        else:
                            self.status.set(f"Stopped / failed (exit code {code}) - see the log below")
                            self.log_line(f"[ui] training process exited with code {code}")
                    elif tag == "chat_exit":
                        self.chat_ready = self.chat_busy = False
                        self.chat_status.set(f"Model process ended (code {item[1]})")
                        self.load_btn.configure(state="normal")
                        self.unload_btn.configure(state="disabled")
                        self.send_btn.configure(state="disabled")
            except queue.Empty:
                pass
            self.root.after(100, self.poll)

        def poll_gpu(self):
            if not self.gpu_busy:
                self.gpu_busy = True
                threading.Thread(target=self.gpu_worker, daemon=True).start()
            self.root.after(3000, self.poll_gpu)

        def gpu_worker(self):
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW if os.name == "nt" else 0)
                u, mu, mt, tmp = [x.strip() for x in res.stdout.strip().splitlines()[0].split(",")]
                self.q.put(("gpu", f"GPU {u}%   |   VRAM {mu} / {mt} MiB   |   {tmp} C"))
            except Exception:
                self.q.put(("gpu", "GPU stats unavailable"))
            finally:
                self.gpu_busy = False

        def on_close(self):
            if self.running():
                if not messagebox.askyesno("Training is running", "Quit and stop training? (Use 'Stop & save' first to keep progress.)"):
                    return
                self.proc.terminate()
            if self.chat_proc and self.chat_proc.poll() is None:
                self.chat_proc.terminate()
            self.root.destroy()

    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if os.name == "nt" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()

def main():
    global JSON_MODE
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=f"{MODEL_NAME} trainer")
    ap.add_argument("mode", nargs="?", default="ui", choices=["ui", "train", "chat", "serve", "merge"])
    ap.add_argument("--data", default="input_data")
    ap.add_argument("--out", default="moneysprout-26-out")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--max-len", type=int, default=1536)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch-size", type=int, default=2, help="per-step batch; lower to 1 if you run out of VRAM")
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--n-forecaster", type=int, default=0, help="0 = use all (1230)")
    ap.add_argument("--n-sentiment", type=int, default=10000, help="0 = use all (16k)")
    ap.add_argument("--n-headlines", type=int, default=50000, help="more = much slower")
    ap.add_argument("--eval-size", type=int, default=100)
    ap.add_argument("--eval-every", type=int, default=200)
    ap.add_argument("--save-steps", type=int, default=50)
    ap.add_argument("--max-steps", type=int, default=-1, help="stop after N optimizer steps (-1 = off)")
    ap.add_argument("--max-minutes", type=float, default=0, help="stop & save after N minutes (0 = off)")
    ap.add_argument("--max-new-tokens", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--json-progress", action="store_true", help="used by the UI")
    a = ap.parse_args()
    JSON_MODE = a.json_progress or a.mode == "serve"
    {"ui": cmd_ui, "train": cmd_train, "chat": cmd_chat, "serve": cmd_serve, "merge": cmd_merge}[a.mode](a)


if __name__ == "__main__":
    main()