"""
API 凭证验证模块。

作用：
    - 使用给定的 SecretId / SecretKey 调用 DescribeRegions，验证凭证与网络连通性。
    - 返回友好的错误提示，便于在设置界面快速定位问题。
"""
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cvm.v20170312 import cvm_client, models
try:
    from config.config_manager import API_ENDPOINT
except ImportError:
    API_ENDPOINT = "cvm.tencentcloudapi.com"


def validate_api(secret_id, secret_key, region):
    """
    验证 API 凭证有效性。

    通过调用 DescribeRegions 判断凭证/网络是否可用。
    """
    if not secret_id or not secret_key:
        return False, "SecretId和SecretKey不能为空"
    
    try:
        # 构造客户端：指定 endpoint，避免默认域名不一致导致的连接问题
        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = API_ENDPOINT
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        client = cvm_client.CvmClient(cred, region, client_profile)

        # 选择开销极小的 DescribeRegions 作为健康检查
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
