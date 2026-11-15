# MoneySprout
**Track:** Finance
**Team:** Nickolas Bogert and Thi Minh Chau Pham

**To use it, go to https://moneysprout.renengine.com** (the site is hosted there, so you do not need to install anything to try it)

# The problem
Lots of teens and first-timers are curious about stocks but have nowhere safe to try things out. Real trading can cost real money, and most beginner tools are confusing or built for experts. Learning by doing matters, so we wanted a place where mistakes are free.

# What we built
MoneySprout is a practice stock market. You sign up, get $10,000 of pretend money, and trade real companies at real (slightly delayed) prices. You can zoom around price charts, draw on them, keep a watchlist, write notes about why you made a move, and look back later to see if you were right.

There is also a forecast. It goes in as a company's recent prices plus its recent news headlines, and comes out as a dashed forecast line with a shaded range, a mood score for the news, and a short written summary. Under 18s need a parent or guardian on the account.

# What we added
Our own idea.

# How it works
**Data:** Prices come from Yahoo Finance. News comes from Yahoo Finance search and Google News (7 searches per company, newest 45 headlines kept, repeats removed). To train the AI adapter we used three public Hugging Face datasets (about 10K lines in total, see Sources). To test headline reading we wrote 63 headlines by hand and labeled them: 20 good, 20 bad, 15 routine and 8 not about the business. Those 63 were never used for training.

**Model:** Three parts work together.
- A keyword scorer plus context rules reads each headline (this always runs, it is simple and easy to check).
- A small AI (Qwen2.5-3B-Instruct with a LoRA adapter we trained) can double check the key headlines and give its own outlook. If it fails, the app falls back to the plain version.
- A forecast function turns the mood score and the price trend into the dashed line and the shaded range.

We chose the keyword approach first because it is cheap and you can see exactly why it said what it said. We added the adapter on top because a small model can handle wording the keyword list misses.

# Results
**Headline reading (63 held-out headlines):** our baseline of always guessing the biggest group scored **31.7%** (20 of 63). Keywords alone scored 79.4%. Our model (keywords plus context rules) scored **87.3%** (55 of 63, likely range 77 to 93%). Out of the 40 clearly good or bad headlines, none were flipped to the opposite direction.

**Forecast (1,000 fake stocks per row):** our baseline of "price stays the same" missed the 30 day end price by 8.33%. The model missed by 8.43%. So the forecast does **not** beat the baseline, and its direction is right about 50% of the time, which is a coin flip. The shaded range hit 80.4% when the fake stocks behaved normally (it promises 80%), but only 41.7% when they suddenly got jumpier.

**The AI adapter:** not measured yet. We did not have the base model or torch where we tested. `analysis-tests/run5_adapter.py` does the comparison.

**Where it fails, and why we think so:**
- Words with two meanings fool the keyword list ("fall" the season), and a good word plus a bad word cancel out.
- Some non-business headlines slip through because they have no listed entertainment word.
- The range is far too narrow after a sudden jump in volatility, because it only knows the past.
- We tested the forecast on fake prices, so it says nothing yet about real markets.

You can rerun all of this with `python analysis-tests/baseline.py`. The full walkthrough is on the "Under the Hood" page of the site.

# What we'd do next
1. Run the adapter test (run5_adapter.py) and a real-price backtest, many stocks over several years using only headlines that existed at the time, compared against buy-and-hold and "no change".
2. Fix the known keyword gaps ("fined", "better than expected", "shows") and test on a few hundred real headlines instead of 63 hand-written ones.

# Sources
**Data and feeds**
- Yahoo Finance chart and search feeds (unofficial): https://finance.yahoo.com
- Google News RSS (unofficial): https://news.google.com

**Training datasets (Hugging Face)**
- FinGPT forecaster, Dow 30, May 2023 to May 2024: https://huggingface.co/datasets/FinGPT/fingpt-forecaster-dow30-202305-202405
- news_with_gpt_instructions: https://huggingface.co/datasets/oliverwang15/news_with_gpt_instructions
- financial-news-articles: https://huggingface.co/datasets/ashraq/financial-news-articles

**Models and tools**
- Qwen2.5-3B-Instruct (base model): https://huggingface.co/Qwen/Qwen2.5-3B-Instruct
- LoRA through Hugging Face PEFT and Transformers: https://huggingface.co/docs/peft
- FastAPI: https://fastapi.tiangolo.com
- Inter and JetBrains Mono fonts (licenses are in frontend/fonts)
- Cloudflare Tunnel, used to host the site

**AI tools used:** TODO, Nickolas and Chau please list any AI tools you used to help write code or text here, with links.

# Run it yourself
Most people should just use https://moneysprout.renengine.com. If you want to run your own copy:

    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    .\start-moneysprout.ps1

To turn the AI adapter on you also need `pip install torch transformers peft`.

by Nickolas Bogert and Thi Minh Chau Pham
