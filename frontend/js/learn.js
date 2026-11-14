// learn page, lessons + glossary + quiz (all static content)

const LESSONS = [
  ['What is a stock?',
   'A stock is a tiny piece of ownership in a company. If a company is split into a million shares and you own one, you own one millionth of it. Companies sell shares to raise money, and people buy them hoping the company does well.'],
  ['What is a stock exchange?',
   'A stock exchange is a marketplace where shares are bought and sold, like the New York Stock Exchange (NYSE) or the NASDAQ. Buyers and sellers agree on a price, and that price is what you see on a chart.'],
  ['What does a ticker symbol mean?',
   'A ticker is a short code for a company. Apple is AAPL and Tesla is TSLA. Tickers make it quick to look up the right company.'],
  ['What makes stock prices change?',
   'Prices move when more people want to buy than sell, or the other way around. Things that change what people want include company earnings, new products, news, interest rates, and how people feel about the economy. Sometimes prices move for reasons nobody fully understands.'],
  ['What is a dividend?',
   'Some companies share part of their profit with their shareholders as regular payments called dividends. Not every company pays them. Many fast growing companies keep the money to grow instead.'],
  ['What is market capitalization?',
   'Market cap is the total value of all of a company\'s shares. You get it by multiplying the share price by the number of shares. It tells you how big a company is, which is not the same as how high one share costs.'],
  ['Bull markets and bear markets',
   'A bull market is a long stretch where prices mostly go up. A bear market is when prices fall a lot, often 20 percent or more from a recent high. Both are normal and have happened many times.'],
  ['What is risk?',
   'Risk is the chance that you lose some or all of the money you put in. Stocks can go down as well as up, and past performance does not tell you what comes next. Only ever invest money you can afford to lose.'],
  ['What is volatility?',
   'Volatility is how much and how fast a price jumps around. A very volatile stock can swing up and down a lot in a short time, which means bigger possible gains but also bigger possible losses.'],
  ['What is diversification?',
   'Diversification means not putting all your money in one place. If you own many different companies, one doing badly hurts less. People often say not to put all your eggs in one basket.'],
  ['Buying and selling shares',
   'When you buy, you pay the current price for each share. When you sell, you get the current price. If you sell for more than you paid you have a profit, and if you sell for less you have a loss. On MoneySprout this is all pretend money.']
];

const GLOSSARY = [
  ['Share', 'One unit of ownership in a company.'],
  ['Ticker', 'A short code that identifies a company on an exchange.'],
  ['Portfolio', 'All the investments a person owns.'],
  ['Dividend', 'A payment some companies make to shareholders.'],
  ['Volume', 'How many shares were traded in a period of time.'],
  ['Market cap', 'Share price multiplied by the number of shares.'],
  ['Volatility', 'How much a price moves up and down.'],
  ['Bull market', 'A time when prices are mostly rising.'],
  ['Bear market', 'A time when prices are falling a lot.'],
  ['Diversification', 'Spreading money across many investments.'],
  ['Profit', 'Money you gain when you sell for more than you paid.'],
  ['Loss', 'Money you lose when you sell for less than you paid.'],
  ['Index', 'A group of stocks used to measure how part of the market is doing, like the S&P 500.'],
  ['Watchlist', 'A list of companies you want to keep an eye on.']
];

const QUIZ = [
  ['What does owning a share of a company mean?',
   ['You own a small piece of the company', 'You work for the company', 'The company owes you money'], 0],
  ['What does a ticker symbol like AAPL do?',
   ['It is the price of a share', 'It is a short code for a company', 'It is the name of the CEO'], 1],
  ['If a stock price went up yesterday, what will it do tomorrow?',
   ['It will go up again', 'It will go down', 'Nobody can know for sure'], 2],
  ['Why do people diversify?',
   ['So one bad investment hurts less', 'To guarantee a profit', 'Because it is the law'], 0],
  ['What is volatility?',
   ['The company\'s profit', 'How much a price jumps around', 'The number of shares a company has'], 1]
];

let qi = 0;
let score = 0;

function renderLessons() {
  document.getElementById('lessons').innerHTML = LESSONS.map(function (l) {
    return '<details class="lesson"><summary>' + esc(l[0]) + '</summary><div class="body">' + esc(l[1]) + '</div></details>';
  }).join('');
}

function renderGlossary() {
  const q = document.getElementById('gsearch').value.trim().toLowerCase();
  const items = GLOSSARY.filter(function (g) {
    return !q || g[0].toLowerCase().includes(q) || g[1].toLowerCase().includes(q);
  });
  document.getElementById('glossary').innerHTML = items.length
    ? items.map(function (g) {
        return '<div class="row" style="display:block"><b>' + esc(g[0]) + '</b><div class="muted">' + esc(g[1]) + '</div></div>';
      }).join('')
    : '<div class="empty small">No words matched.</div>';
}

function renderQuiz() {
  const box = document.getElementById('quiz');
  if (qi >= QUIZ.length) {
    box.innerHTML = '<p><b>You got ' + score + ' out of ' + QUIZ.length + '.</b></p>' +
      '<p class="muted">' + (score === QUIZ.length ? 'Perfect score!' : 'Look back at the lessons and try again.') + '</p>' +
      '<button class="btn" id="again">Try again</button>';
    document.getElementById('again').onclick = function () { qi = 0; score = 0; renderQuiz(); };
    return;
  }
  const q = QUIZ[qi];
  box.innerHTML = '<p class="muted small">Question ' + (qi + 1) + ' of ' + QUIZ.length + '</p><p><b>' + esc(q[0]) + '</b></p>' +
    q[1].map(function (o, i) {
      return '<button class="btn light quiz-opt" data-i="' + i + '">' + esc(o) + '</button>';
    }).join('') + '<div id="fb" class="small"></div>';

  let answered = false;
  box.querySelectorAll('.quiz-opt').forEach(function (b) {
    b.onclick = function () {
      if (answered) return;
      answered = true;
      const pick = Number(b.dataset.i);
      box.querySelectorAll('.quiz-opt').forEach(function (x) {
        if (Number(x.dataset.i) === q[2]) x.classList.add('right-ans');
      });
      if (pick === q[2]) score++;
      else b.classList.add('wrong-ans');
      document.getElementById('fb').innerHTML = (pick === q[2] ? 'Correct!' : 'Not quite.') +
        ' <button class="btn sm" id="next" style="margin-left:8px">' + (qi === QUIZ.length - 1 ? 'See score' : 'Next') + '</button>';
      document.getElementById('next').onclick = function () { qi++; renderQuiz(); };
    };
  });
}

async function start() {
  await initShell('learn.html');
  renderLessons();
  renderGlossary();
  renderQuiz();
  document.getElementById('gsearch').addEventListener('input', renderGlossary);
}

start();
