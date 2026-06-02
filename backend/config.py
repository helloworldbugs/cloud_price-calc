COUNTRY_CITY_MAP = {
    "中国": {
        "杭州": {"aliyun": "cn-hangzhou", "tencent": "ap-guangzhou", "huawei": "cn-east-2"},
        "上海": {"aliyun": "cn-shanghai", "tencent": "ap-shanghai", "huawei": "cn-east-3"},
        "北京": {"aliyun": "cn-beijing", "tencent": "ap-beijing", "huawei": "cn-north-4"},
        "深圳": {"aliyun": "cn-shenzhen", "tencent": "ap-guangzhou", "huawei": "cn-south-1"},
        "广州": {"aliyun": "cn-guangzhou", "tencent": "ap-guangzhou", "huawei": "cn-south-1"},
        "成都": {"aliyun": "cn-chengdu", "tencent": "ap-chengdu", "huawei": "cn-southwest-2"},
        "南京": {"aliyun": "cn-nanjing", "tencent": "ap-nanjing", "huawei": "cn-east-2"},
        "香港": {"aliyun": "cn-hongkong", "tencent": "ap-hongkong", "huawei": "ap-southeast-1"},
    },
    "新加坡": {
        "新加坡": {"aliyun": "ap-southeast-1", "tencent": "ap-singapore", "huawei": "ap-southeast-1"},
    },
    "日本": {
        "东京": {"aliyun": "ap-northeast-1", "tencent": "ap-tokyo", "huawei": "ap-northeast-1"},
    },
    "美国": {
        "硅谷": {"aliyun": "us-west-1", "tencent": "na-siliconvalley", "huawei": "na-mexico-1"},
        "弗吉尼亚": {"aliyun": "us-east-1", "tencent": "na-ashburn", "huawei": "na-mexico-1"},
    },
    "德国": {
        "法兰克福": {"aliyun": "eu-central-1", "tencent": "eu-frankfurt", "huawei": "eu-west-0"},
    },
}

SPECS = [
    {"cpu": 1, "mem": 1, "label": "1核1G"},
    {"cpu": 1, "mem": 2, "label": "1核2G"},
    {"cpu": 2, "mem": 4, "label": "2核4G"},
    {"cpu": 2, "mem": 8, "label": "2核8G"},
    {"cpu": 4, "mem": 8, "label": "4核8G"},
    {"cpu": 4, "mem": 16, "label": "4核16G"},
    {"cpu": 8, "mem": 16, "label": "8核16G"},
    {"cpu": 8, "mem": 32, "label": "8核32G"},
    {"cpu": 16, "mem": 32, "label": "16核32G"},
    {"cpu": 16, "mem": 64, "label": "16核64G"},
    {"cpu": 32, "mem": 64, "label": "32核64G"},
    {"cpu": 32, "mem": 128, "label": "32核128G"},
    {"cpu": 64, "mem": 128, "label": "64核128G"},
    {"cpu": 64, "mem": 256, "label": "64核256G"},
    {"cpu": 96, "mem": 192, "label": "96核192G"},
    {"cpu": 96, "mem": 384, "label": "96核384G"},
    {"cpu": 128, "mem": 256, "label": "128核256G"},
    {"cpu": 128, "mem": 512, "label": "128核512G"},
]

DISK_OPTIONS = [40, 50, 100, 200, 500, 1000]

BANDWIDTH_OPTIONS = [1, 2, 5, 10, 20, 50, 100, 200, 500]

ALIYUN_INSTANCE_MAP = {
    (1, 1): "ecs.t6-c1m1.large",
    (1, 2): "ecs.t6-c1m2.large",
    (2, 4): "ecs.c7.large",
    (2, 8): "ecs.r7.large",
    (4, 8): "ecs.c7.xlarge",
    (4, 16): "ecs.r7.xlarge",
    (8, 16): "ecs.c7.2xlarge",
    (8, 32): "ecs.r7.2xlarge",
    (16, 32): "ecs.c7.4xlarge",
    (16, 64): "ecs.r7.4xlarge",
    (32, 64): "ecs.c7.8xlarge",
    (32, 128): "ecs.r7.8xlarge",
    (64, 128): "ecs.c7.16xlarge",
    (64, 256): "ecs.r7.16xlarge",
    (96, 192): "ecs.g7.24xlarge",
    (96, 384): "ecs.r7.24xlarge",
    (128, 256): "ecs.g7.32xlarge",
    (128, 512): "ecs.r7.32xlarge",
}

TENCENT_INSTANCE_MAP = {
    (1, 1): "S6.SMALL1",
    (1, 2): "S6.SMALL2",
    (2, 4): "S6.MEDIUM4",
    (2, 8): "S6.MEDIUM8",
    (4, 8): "S6.LARGE8",
    (4, 16): "S6.LARGE16",
    (8, 16): "S6.2XLARGE16",
    (8, 32): "S6.2XLARGE32",
    (16, 32): "S6.4XLARGE32",
    (16, 64): "S6.4XLARGE64",
    (32, 64): "S6.8XLARGE64",
    (32, 128): "S6.8XLARGE128",
    (64, 128): "S6.16XLARGE128",
    (64, 256): "S6.16XLARGE256",
    (96, 192): "S6.24XLARGE192",
    (96, 384): "S6.24XLARGE384",
    (128, 256): "S6.32XLARGE256",
    (128, 512): "S6.32XLARGE512",
}

HUAWEI_INSTANCE_MAP = {
    (1, 1): "s6.small.1",
    (1, 2): "s6.small.2",
    (2, 4): "s6.large.4",
    (2, 8): "s6.large.8",
    (4, 8): "s6.xlarge.8",
    (4, 16): "s6.xlarge.16",
    (8, 16): "s6.2xlarge.16",
    (8, 32): "s6.2xlarge.32",
    (16, 32): "s6.4xlarge.32",
    (16, 64): "s6.4xlarge.64",
    (32, 64): "s6.8xlarge.64",
    (32, 128): "s6.8xlarge.128",
    (64, 128): "s6.16xlarge.128",
    (64, 256): "s6.16xlarge.256",
    (96, 192): "s6.24xlarge.192",
    (96, 384): "s6.24xlarge.384",
    (128, 256): "s6.32xlarge.256",
    (128, 512): "s6.32xlarge.512",
}

ALIYUN_DISK_CATEGORY = "cloud_essd"
TENCENT_DISK_TYPE = "CLOUD_BSSD"
HUAWEI_DISK_TYPE = "SAS"
