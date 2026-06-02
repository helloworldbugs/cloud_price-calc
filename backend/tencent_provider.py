import httpx
import time
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": "https://buy.cloud.tencent.com",
    "Referer": "https://buy.cloud.tencent.com/price/cvm",
    "x-referer": "https://buy.cloud.tencent.com/price/cvm",
    "x-intl": "false",
    "x-csrfcode": "",
    "x-seqid": "00000000-0000-0000-0000-000000000000",
    "x-lid": "auto-compare",
}

_client = None
_instance_cache = {}


async def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    return _client


async def get_instance_types(region_id: str) -> list:
    if region_id in _instance_cache:
        return _instance_cache[region_id]
    client = await _get_client()
    headers = {**HEADERS, "x-life": str(int(time.time() * 1000))}
    url = "https://workbench.cloud.tencent.com/cgi/api"
    params = {"i": "cvm/DescribeZoneInstanceConfigInfos", "uin": "", "region": region_id}
    body = {
        "serviceType": "cvm",
        "action": "DescribeZoneInstanceConfigInfos",
        "region": region_id,
        "data": {
            "Filters": [{"Name": "instance-charge-type", "Values": ["PREPAID"]}],
            "Platform": "LINUX",
            "Version": "2017-03-12",
        },
        "cgiName": "api",
    }
    try:
        resp = await client.post(url, headers=headers, json=body, params=params)
        data = resp.json()
        instances = data.get("data", {}).get("Response", {}).get("InstanceTypeQuotaSet", [])
        result = []
        for inst in instances:
            c = inst.get("Cpu", 0)
            m = inst.get("Memory", 0)
            if c > 0 and m > 0:
                price_info = inst.get("Price", {})
                monthly = price_info.get("DiscountPrice", 0) or price_info.get("OriginalPrice", 0)
                result.append({"cpu": c, "mem": m, "instance_type": inst.get("InstanceType", ""), "price": round(float(monthly), 2)})
        _instance_cache[region_id] = result
        return result
    except Exception:
        logger.exception("Failed to fetch Tencent instance types for region %s", region_id)
        return []


def _group_cheapest(instances: list) -> dict:
    groups = {}
    for inst in instances:
        key = (inst["cpu"], inst["mem"])
        if key not in groups or inst["price"] < groups[key]["price"]:
            groups[key] = inst
    return groups


async def query_all_prices(region_id: str):
    instances = await get_instance_types(region_id)
    if not instances:
        return []
    groups = _group_cheapest(instances)
    return [{"provider": "腾讯云", "instance_type": inst["instance_type"],
             "cpu": inst["cpu"], "mem": inst["mem"], "monthly_price": inst["price"], "currency": "CNY"}
            for inst in groups.values()]


async def query_price(region_id: str, cpu: int, mem: int):
    instances = _instance_cache.get(region_id, [])
    if not instances:
        await get_instance_types(region_id)
        instances = _instance_cache.get(region_id, [])

    matching = [inst for inst in instances if inst["cpu"] == cpu and inst["mem"] == mem]
    if not matching:
        return {"provider": "腾讯云", "error": f"该地域无 {cpu}核{mem}G 的实例规格"}

    cheapest = min(matching, key=lambda x: x["price"])
    return {"provider": "腾讯云", "instance_type": cheapest["instance_type"],
            "monthly_price": cheapest["price"], "currency": "CNY"}
