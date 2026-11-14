instructions (how to use :P)


cd MoneySprout
python -m venv venv
venv\Scripts\activate         
pip install -r requirements.txt

cloudflared tunnel login
cloudflared tunnel create moneysprout
cloudflared tunnel route dns moneysprout moneysprout.renengine.com

.\start-moneysprout.ps1