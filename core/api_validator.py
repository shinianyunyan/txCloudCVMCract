"""
API凭证验证模块
"""
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cvm.v20170312 import cvm_client, models
from config.config import API_ENDPOINT


def validate_api(secret_id, secret_key, region):
    """验证API凭证是否有效"""
    if not secret_id or not secret_key:
        return False, "SecretId和SecretKey不能为空"
    
    try:
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = API_ENDPOINT
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        client = cvm_client.CvmClient(cred, region, client_profile)
        req = models.DescribeRegionsRequest()
        resp = client.DescribeRegions(req)
        
        if resp and resp.RegionSet:
            return True, "API凭证验证成功"
        else:
            return False, "API调用返回异常"
    except Exception as e:
        error_msg = str(e)
        if "InvalidCredential" in error_msg or "AuthFailure" in error_msg:
            return False, "API凭证无效，请检查SecretId和SecretKey"
        elif "RequestLimitExceeded" in error_msg:
            return False, "API调用频率过高，请稍后再试"
        elif "NetworkError" in error_msg or "Connection" in error_msg:
            return False, "网络连接失败，请检查网络设置"
        else:
            return False, f"验证失败: {error_msg}"
