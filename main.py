from h11 import Request
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import uvicorn
from pydantic import BaseModel
import requests
import aiohttp
import asyncio
import json
from nacl.bindings import crypto_sign
from datetime import datetime
import aiolimiter
import logging
import sys
import os
from dotenv import load_dotenv



logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class SkinItem(BaseModel):
    name: str=''
    price_lf: float=0.00001
    price_dm: float=0.00001
    num: int = 1
    max_order:float=0.00001
    lf_to_steam: float = 0
    profit_to_dm: float = -100
    profit_to_lf: float = -100
    overstock_lf:int=0


load_dotenv()

public_key = os.getenv("DMARKET_PUBLIC_KEY")
secret_key = os.getenv("DMARKET_SECRET_KEY")
rusttm_key = os.getenv("RUSTTM_API_KEY")



app = FastAPI()

templates = Jinja2Templates(directory="templates")
dmarket_limiter = aiolimiter.AsyncLimiter(10, 1)


def get_lootfarm(num=0):
    try:
        parsed_data=[]
        url = "https://loot.farm/fullpriceRUST.json"
        response = requests.get(url)
        for i in response.json():
            item = SkinItem(name=i['name'],price_lf=i['price']/100,num=i['have'],overstock_lf=i['max'],lf_to_steam=i['rate']/100)
            parsed_data.append(item)
        return [a for a in parsed_data if a.num>num and a.price_lf>=2 and a.price_lf<=10 and a.overstock_lf>0]
    except Exception as e:
        print(f"Ошибка при парсинге lootfarm: {e}")
        return []


async def make_signed_request(method, path, body=None):
    async with dmarket_limiter:
        nonce = str(round(datetime.now().timestamp()))
        body_str = json.dumps(body) if body else json.dumps({})
        string_to_sign = method + path + nonce
        #print(string_to_sign)
        
        encoded = string_to_sign.encode('utf-8')
        secret_bytes = bytes.fromhex(secret_key)
        signature_bytes = crypto_sign(encoded, secret_bytes)
        signature = signature_bytes[:64].hex()
        
        headers = {
            "X-Api-Key": public_key,
            "X-Request-Sign": "dmar ed25519 " + signature,
            "X-Sign-Date": nonce,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        url = "https://api.dmarket.com" + path
        # logger.info(f"запрос")
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, timeout=20) as response:
                        return await response.json()
                else:
                    async with session.get(url, headers=headers, timeout=20) as response:
                        return await response.json()
        except Exception as e:
            print(f"Request error: {e}")
            return None
    

async def get_dmarket_item_data(item: SkinItem):
    search_path1 = f"/exchange/v1/offers-by-title?title={item.name}&limit=50"
    search_path2 = f"/marketplace-api/v1/targets-by-title/rust/{item.name}"

    
    response1 = await make_signed_request("GET", search_path1)
    response2 = await make_signed_request("GET", search_path2)

    try:
        if response1 and 'objects' in response1:
            arr = response1['objects']
            # logger.info(f"ответ")
            if arr:
                offers = [a for a in arr if a['title'] == item.name]
                if offers:
                    offer = min(offers, key=lambda x: float(x['price']['USD']))
                    item.price_dm = float(offer['price']['USD']) / 100
    except Exception as e:
        print(f"Error processing response1 for {item.name}: {e}")
    
    try:
        if response2 and 'orders' in response2:
            arr = response2['orders']
            if arr:
                item.max_order = float(arr[0]['price']) / 100
    except Exception as e:
        print(f"Error processing response2 for {item.name}: {e}")
    
    return item

async def get_dmarket(items: list[SkinItem]):
    tasks = [get_dmarket_item_data(item) for item in items]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    
    successful_results = []
    for result in results:
        if not isinstance(result, Exception):
            successful_results.append(result)
        else:
            print(f"Error in task: {result}")
    
    return successful_results  

def get_rusttm_prices(items:list[SkinItem]):
    try:
        parsed_data=[]
        url = "https://rust.tm/api/v2/prices/class_instance/USD.json"
        headers ={'X-API-KEY':rusttm_key}

        response = requests.get(url=url,headers=headers)
        rusttm_items = response.json()['items']
        for i in items:
            item = [a for a in rusttm_items.values() if a['market_hash_name']==i.name]
            if item:
                item = item[0]
            else:
                continue
            i.price_dm = float(item['price'])
            i.max_order = float(item['buy_order'])
        return items

    except Exception as e:
        print(f"Ошибка при парсинге rusttm: {e}")
        return []

def get_profits(items:list[SkinItem]):
    items = [i for i in items if i.max_order>0.01 and i.price_dm>0.01]
    for i in items:
        i.profit_to_lf=i.price_lf*100/i.price_dm-108
        i.profit_to_dm=i.max_order*100/i.price_lf-105
    
    return items


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "data": []
    })


@app.post("/parse")
async def parse_data():
    try:
        logger.info(f"старт")
        data = get_lootfarm()
        print(len(data))
        data = await get_dmarket(data)
        data = get_profits(data)
        logger.info(f"конец")
    except Exception as e:
        print('err')

    return data

@app.post("/parsetm")
async def parse_data():
    try:
        logger.info(f"старт")
        data = get_lootfarm(num=-1)
        print(len(data))
        data = get_rusttm_prices(data)
        data = get_profits(data)
        logger.info(f"конец")
    except Exception as e:
        print('err')

    return data

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host='0.0.0.0',
        port=int(os.getenv("PORT") or 8000),
        reload=False
    )
    
