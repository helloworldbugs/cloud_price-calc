import httpx
import re
import asyncio
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Referer": "https://www.aliyun.com/price/product",
    "Origin": "https://www.aliyun.com",
    "Accept": "application/json, text/plain, */*",
}

_SIZE_TO_VCPU = {
    "large": 2, "xlarge": 4,
    "2xlarge": 8, "3xlarge": 12, "4xlarge": 16, "5xlarge": 20,
    "6xlarge": 24, "7xlarge": 28, "8xlarge": 32, "9xlarge": 36,
    "10xlarge": 40, "11xlarge": 44, "12xlarge": 48, "13xlarge": 52,
    "14xlarge": 56, "15xlarge": 60, "16xlarge": 64, "17xlarge": 68,
    "18xlarge": 72, "19xlarge": 76, "20xlarge": 80, "21xlarge": 84,
    "22xlarge": 88, "23xlarge": 92, "24xlarge": 96, "25xlarge": 100,
    "26xlarge": 104, "27xlarge": 108, "28xlarge": 112, "29xlarge": 116,
    "30xlarge": 120, "31xlarge": 124, "32xlarge": 128, "33xlarge": 132,
    "34xlarge": 136, "35xlarge": 140, "36xlarge": 144, "40xlarge": 160,
    "48xlarge": 192, "56xlarge": 224, "64xlarge": 256, "96xlarge": 384,
    "small": 1, "medium": 1, "micro": 1, "nano": 1,
}

_client = None
_csrf_token = None
_instance_cache = {}


def _parse_instance_type(name: str):
    parts = name.split(".")
    if len(parts) < 3:
        return 0, 0
    family = parts[1]
    size = parts[2]
    cpu = _SIZE_TO_VCPU.get(size, 0)
    if cpu == 0:
        m = re.match(r"(\d+)xlarge", size)
        if m:
            cpu = int(m.group(1)) * 4
    if cpu == 0:
        return 0, 0

    m2 = re.search(r"c(\d+)m(\d+)", family)
    if m2:
        n = int(m2.group(1))
        mem_m = int(m2.group(2))
        mem_ratio = mem_m / n
    else:
        mem_ratio = 4
        if family.startswith("c"):
            mem_ratio = 2
        elif family.startswith("r"):
            mem_ratio = 8
        elif family.startswith("g"):
            mem_ratio = 4

    mem = cpu * mem_ratio
    if mem < 1:
        mem = round(mem, 2)
    return cpu, mem


async def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    return _client


async def _ensure_csrf():
    global _csrf_token
    if _csrf_token:
        return _csrf_token
    client = await _get_client()
    resp = await client.get("https://www.aliyun.com/price/product", headers=HEADERS)
    for cookie in client.cookies.jar:
        if cookie.name == "XSRF-TOKEN" or cookie.name == "buy_api_csrf_token":
            _csrf_token = cookie.value
            break
    if not _csrf_token:
        for cookie in client.cookies.jar:
            if "csrf" in cookie.name.lower() or "xsrf" in cookie.name.lower():
                _csrf_token = cookie.value
                break
    return _csrf_token


async def _get_commodity_data(region_id: str):
    client = await _get_client()
    url = "https://buy-api.aliyun.com/commodity/getCommodity.json"
    params = {
        "commodityCode": "bards",
        "orderType": "BUY",
        "commodityParams": "{}",
        "channel": "calculator",
        "request": '{"rds_region":"' + region_id + '"}',
    }
    try:
        resp = await client.get(url, headers=HEADERS, params=params)
        data = resp.json()
        if data.get("code") == "200":
            return data.get("data", {})
    except Exception:
        logger.exception("Failed to fetch Aliyun RDS commodity data for region %s", region_id)
    return None


async def get_instance_types(region_id: str) -> list:
    if region_id in _instance_cache:
        return _instance_cache[region_id]

    commodity_data = await _get_commodity_data(region_id)
    if not commodity_data:
        return []

    components = commodity_data.get("components", {})
    rds_class = components.get("rds_class", {}).get("rds_class", [])

    result = []
    for c in rds_class:
        text = c.get("text", "")
        value = c.get("value", "")
        if not value or not value.startswith("mysql."):
            continue

        m = re.search(r"(\d+)\s*核\s*(\d+)\s*[GgMm]", text)
        if m:
            cpu = int(m.group(1))
            mem = int(m.group(2))
            if cpu > 0 and mem > 0:
                result.append({"cpu": cpu, "mem": mem, "instance_type": value})
        else:
            cpu, mem = _parse_instance_type(value)
            if cpu > 0 and mem > 0:
                result.append({"cpu": cpu, "mem": mem, "instance_type": value})

    _instance_cache[region_id] = result
    return result


async def _query_one_price(client, csrf, region_id, instance_type):
    headers = {**HEADERS}
    if csrf:
        headers["x-xsrf-token"] = csrf

    body = {
        "tenant": "TenantCalculator",
        "channel": "calculator",
        "bizOccasion": "calculator",
        "orderOrBilling": "order",
        "configurations": [{
            "commodityCode": "bards",
            "specCode": "bards",
            "commodityName": "云数据库RDS-按量付费",
            "chargeType": "POSTPAY",
            "orderType": "BUY",
            "quantity": 1,
            "pricingCycle": "Hour",
            "duration": "1",
            "components": [
                {"componentCode": "rds_region", "instanceProperty": [{"code": "rds_region", "value": region_id}]},
                {"componentCode": "rds_dbtype", "instanceProperty": [{"code": "rds_dbtype", "value": "mysql"}]},
                {"componentCode": "rds_dbversion", "instanceProperty": [{"code": "rds_dbversion", "value": "8.0"}]},
                {"componentCode": "rds_nodetype", "instanceProperty": [{"code": "rds_nodetype", "value": "Basic"}]},
                {"componentCode": "rds_class", "instanceProperty": [{"code": "rds_class", "value": instance_type}]},
                {"componentCode": "rds_storage", "instanceProperty": [{"code": "rds_storage", "value": "20"}]},
                {"componentCode": "rds_storagetype", "instanceProperty": [{"code": "rds_storagetype", "value": "cloud_essd"}]},
            ]
        }]
    }
    try:
        resp = await client.post("https://buy-api.aliyun.com/price/getLightWeightPrice2.json",
            headers=headers, json=body, params={"tenant": "TenantCalculator"}, timeout=15)
        data = resp.json()
        if data.get("code") == "200" and data.get("data"):
            order = data["data"].get("order", {})
            order_lines = order.get("orderLines", {})
            instance_hourly = 0
            for key, line in order_lines.items():
                for mi in line.get("moduleInstance", []):
                    if mi.get("moduleCode") == "rds_class":
                        instance_hourly = float(mi.get("payFee", 0)) / 100
                        break
                if instance_hourly > 0:
                    break
            if instance_hourly > 0:
                monthly = round(instance_hourly * 730, 2)
                return {
                    "monthly_price": monthly,
                    "hourly_price": round(instance_hourly, 4),
                    "is_ondemand": True,
                }
            monthly_hourly = round(float(order.get("tradeAmount", 0)), 2)
            if monthly_hourly > 0:
                return {
                    "monthly_price": round(monthly_hourly * 730, 2),
                    "hourly_price": monthly_hourly,
                    "is_ondemand": True,
                }
    except Exception:
        logger.exception("Failed to query Aliyun RDS price: region=%s instance=%s", region_id, instance_type)
    return None


async def query_all_prices(region_id: str, concurrency: int = 5):
    instances = await get_instance_types(region_id)
    if not instances:
        return []

    groups = {}
    for inst in instances:
        key = (inst["cpu"], inst["mem"])
        if key not in groups:
            groups[key] = []
        groups[key].append(inst)

    client = await _get_client()
    csrf = await _ensure_csrf()
    sem = asyncio.Semaphore(concurrency)

    async def fetch(inst):
        async with sem:
            price_info = await _query_one_price(client, csrf, region_id, inst["instance_type"])
            if price_info is not None:
                result = {"provider": "阿里云", "instance_type": inst["instance_type"],
                        "cpu": inst["cpu"], "mem": inst["mem"], "currency": "CNY",
                        "region_id": region_id, **price_info}
                return result
            return None

    tasks = [fetch(groups[key][0]) for key in groups]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def query_price(region_id: str, cpu: int, mem: int):
    instances = _instance_cache.get(region_id, [])
    if not instances:
        await get_instance_types(region_id)
        instances = _instance_cache.get(region_id, [])

    matching = [inst for inst in instances if inst["cpu"] == cpu and inst["mem"] == mem]
    if not matching:
        return {"provider": "阿里云", "error": f"该地域无 {cpu}核{mem}G 的RDS规格"}

    client = await _get_client()
    csrf = await _ensure_csrf()

    best = None
    for instance_type in [m["instance_type"] for m in matching]:
        price_info = await _query_one_price(client, csrf, region_id, instance_type)
        if price_info is not None:
            price = price_info.get("monthly_price", float("inf"))
            if best is None or price < best[1]:
                best = (instance_type, price, price_info)

    if best:
        return {"provider": "阿里云", "instance_type": best[0], "cpu": cpu, "mem": mem,
                "currency": "CNY", "region_id": region_id, **best[2]}
    return {"provider": "阿里云", "error": f"查询 {cpu}核{mem}G RDS价格失败"}
