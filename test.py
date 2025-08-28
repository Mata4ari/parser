from ast import List
from urllib import response
from h11 import Request
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
import time
from fastapi.templating import Jinja2Templates
import uvicorn
from pydantic import BaseModel
import re
from typing import Optional
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
    max_order:float=1000
    lf_to_steam: float = 0
    profit_to_dm: float = -100
    profit_to_lf: float = -100
    overstock_lf:int=0

load_dotenv()

public_key = os.getenv("DMARKET_PUBLIC_KEY")
secret_key = os.getenv("DMARKET_SECRET_KEY")
rusttm_key = os.getenv("RUSTTM_API_KEY")





def get_lootfarm():
    try:
        parsed_data=[]
        url = "https://loot.farm/fullpriceRUST.json"
        response = requests.get(url)
        for i in response.json():
            item = SkinItem(name=i['name'],price_lf=i['price']/100,num=i['have'],overstock_lf=i['max'],lf_to_steam=i['rate']/100)
            parsed_data.append(item)
        return [a for a in parsed_data if a.num>0 and a.price_lf>=2 and a.price_lf<=10 and a.overstock_lf>0]
    except Exception as e:
        print(f"Ошибка при парсинге lootfarm: {e}")
        return []


def get_profits(items:list[SkinItem]):
    for i in items:
        i.profit_to_lf=i.price_lf*100/i.price_dm-108
        i.profit_to_dm=i.max_order*100/i.price_lf-105
    return items


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


data = get_lootfarm()
data = get_rusttm_prices(data)
data = get_profits(data)
print(data)