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

_client = None
_csrf_token = None
_instance_cache = {}

SIZE_TO_VCPU = {
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


def _parse_instance_type(name: str):
    parts = name.split(".")
    if len(parts) < 3:
        return 0, 0
    family = parts[1]
    size = parts[2]
    cpu = SIZE_TO_VCPU.get(size, 0)
    if cpu == 0:
        m = re.match(r"(\d+)xlarge", size)
        if m:
            cpu = int(m.group(1)) * 4
    if cpu == 0:
        return 0, 0
    mem_ratio = 4
    if family.startswith("c") or "c1m2" in family:
        mem_ratio = 2
    elif family.startswith("r") or "c1m8" in family:
        mem_ratio = 8
    elif "c1m4" in family:
        mem_ratio = 4
    elif "c1m1" in family:
        mem_ratio = 1
    m2 = re.search(r"c\d+m(\d+)", family)
    if m2:
        mem_ratio = int(m2.group(1))
    return cpu, cpu * mem_ratio


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


async def get_instance_types(region_id: str) -> list:
    if region_id in _instance_cache:
        return _instance_cache[region_id]
    client = await _get_client()
    url = "https://query.aliyun.com/rest/sell.ecs.availableInstanceTypes"
    params = {"regionId": region_id, "domain": "aliyun", "zoneId": "", "saleStrategy": "PrePaid"}
    try:
        resp = await client.get(url, headers=HEADERS, params=params)
        data = resp.json()
        instances_raw = data.get("data", {}).get("optimized", [])
        result = []
        for inst in instances_raw:
            type_name = inst.get("value", "")
            if not type_name:
                continue
            cpu, mem = _parse_instance_type(type_name)
            if cpu > 0 and mem > 0:
                result.append({"cpu": cpu, "mem": mem, "instance_type": type_name})
        _instance_cache[region_id] = result
        return result
    except Exception:
        logger.exception("Failed to fetch Aliyun instance types for region %s", region_id)
        return []


def _find_instance_type(cpu: int, mem: int, instances: list):
    for inst in instances:
        if inst["cpu"] == cpu and inst["mem"] == mem:
            return inst["instance_type"]
    return None


def _find_all_instance_types(cpu: int, mem: int, instances: list):
    return [inst["instance_type"] for inst in instances if inst["cpu"] == cpu and inst["mem"] == mem]


async def _query_one_price(client, csrf, region_id, instance_type):
    headers = {**HEADERS}
    if csrf:
        headers["x-xsrf-token"] = csrf
    body = {
        "tenant": "TenantCalculator", "channel": "calculator", "bizOccasion": "calculator",
        "orderOrBilling": "order",
        "configurations": [{"commodityCode": "vm", "specCode": "vm", "commodityName": "云服务器ECS-包年包月",
            "chargeType": "PREPAY", "orderType": "BUY", "quantity": 1, "pricingCycle": "Month", "duration": "1",
            "components": [
                {"componentCode": "vm_region_no", "instanceProperty": [{"code": "vm_region_no", "value": region_id}]},
                {"componentCode": "instance_type", "instanceProperty": [
                    {"code": "instance_type", "value": instance_type},
                    {"code": "instance_type_family", "value": instance_type.rsplit(".", 1)[0]}]},
                {"componentCode": "vm_os", "instanceProperty": [
                    {"code": "vm_os", "value": "aliyun_3_x64_20G_alibase_20260513.vhd"},
                    {"code": "vm_os_kind", "value": "linux"}, {"code": "vm_os_bit", "value": "64"}]}]}]}
    try:
        resp = await client.post("https://buy-api.aliyun.com/price/getLightWeightPrice2.json",
            headers=headers, json=body, params={"tenant": "TenantCalculator"}, timeout=15)
        data = resp.json()
        if data.get("code") == "200" and data.get("data"):
            order = data["data"].get("order", {})
            trade_amount = order.get("tradeAmount")
            original_amount = order.get("originalAmount")
            amount = trade_amount if trade_amount is not None else original_amount
            if amount is not None:
                result = {"monthly_price": round(float(amount), 2)}
                if original_amount is not None:
                    result["original_monthly_price"] = round(float(original_amount), 2)
                if trade_amount is not None:
                    result["discount_monthly_price"] = round(float(trade_amount), 2)
                return result
    except Exception:
        logger.exception("Failed to query Aliyun price: region=%s instance=%s", region_id, instance_type)
    return None


async def query_all_prices(region_id: str, concurrency: int = 10):
    instances = await get_instance_types(region_id)
    if not instances:
        return []

    groups = {}
    for inst in instances:
        key = (inst["cpu"], inst["mem"])
        if key not in groups:
            groups[key] = inst

    client = await _get_client()
    csrf = await _ensure_csrf()
    sem = asyncio.Semaphore(concurrency)

    async def fetch(inst):
        async with sem:
            price_info = await _query_one_price(client, csrf, region_id, inst["instance_type"])
            if price_info is not None:
                return {"provider": "阿里云", "instance_type": inst["instance_type"],
                        "cpu": inst["cpu"], "mem": inst["mem"], "currency": "CNY",
                        "region_id": region_id, **price_info}
            return None

    tasks = [fetch(inst) for inst in groups.values()]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def query_price(region_id: str, cpu: int, mem: int):
    instances = _instance_cache.get(region_id, [])
    if not instances:
        await get_instance_types(region_id)
        instances = _instance_cache.get(region_id, [])
    matching_types = _find_all_instance_types(cpu, mem, instances) if instances else []
    if not matching_types:
        return {"provider": "阿里云", "error": f"该地域无 {cpu}核{mem}G 的实例规格"}

    client = await _get_client()
    csrf = await _ensure_csrf()

    best = None
    for instance_type in matching_types:
        price_info = await _query_one_price(client, csrf, region_id, instance_type)
        if price_info is not None:
            price = price_info.get("monthly_price", float("inf"))
            if best is None or price < best[1]:
                best = (instance_type, price, price_info)

    if best:
        return {"provider": "阿里云", "instance_type": best[0], "cpu": cpu, "mem": mem,
                "currency": "CNY", "region_id": region_id, **best[2]}
    return {"provider": "阿里云", "error": f"查询 {cpu}核{mem}G 价格失败"}
