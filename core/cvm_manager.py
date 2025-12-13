"""
腾讯云 CVM 实例管理核心类。

职责：
    - 封装 CVM 常用操作：区域/可用区、镜像、机型、价格查询，实例创建/启动/关机/销毁/重置密码。
    - 负责凭证与区域初始化，必要时切换客户端区域并提供资源不足兜底。
    - 统一日志格式，便于排查 API 调用或资源状态问题。
"""
import logging
import time
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cvm.v20170312 import cvm_client, models
# TAT 相关导入改为延迟导入，避免预加载时出错
from utils.utils import setup_logger, validate_password, get_region_name
from utils.db_manager import get_db
try:
    from config.config_manager import get_api_config, API_ENDPOINT
    _use_cfg_mgr = True
except ImportError:
    _use_cfg_mgr = False
    API_ENDPOINT = "cvm.tencentcloudapi.com"


class CVMManager:
    """CVM 实例管理器，封装实例生命周期与查询操作。"""
    
    def __init__(self, secret_id, secret_key, region):
        # 从配置管理器读取默认凭证与区域，参数缺省时兜底
        if _use_cfg_mgr:
            cfg = get_api_config()
            self.secret_id = secret_id or cfg.get("secret_id")
            self.secret_key = secret_key or cfg.get("secret_key")
            self.region = region or cfg.get("default_region", "ap-beijing")
        else:
            # 降级方案：从环境变量读取
            import os
            self.secret_id = secret_id or os.getenv("TENCENT_SECRET_ID")
            self.secret_key = secret_key or os.getenv("TENCENT_SECRET_KEY")
            self.region = region or os.getenv("TENCENT_DEFAULT_REGION", "ap-beijing")
        
        self.logger = setup_logger("CVM_Manager", "cvm_manager.log", "INFO")
        if not self.secret_id or not self.secret_key:
            raise ValueError("请先配置腾讯云API凭证")
        self._init_client(None)
        # TAT客户端延迟初始化，只在需要时（执行命令）才初始化
        self.tat_client = None
        self._tat_models = None
    
    def _init_client(self, region):
        """
        初始化（或切换）CVM 客户端。

        - region 为空则使用当前 region。
        - 若传入新 region，会更新 self.region，后续调用保持一致。
        """
        target_region = region or self.region
        cred = credential.Credential(self.secret_id, self.secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = API_ENDPOINT
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        self.client = cvm_client.CvmClient(cred, target_region, client_profile)
        if region:
            self.region = target_region
        self.logger.info(f"CVM客户端初始化成功，区域: {target_region}")
    
    def _init_tat_client(self):
        """初始化TAT（腾讯云自动化工具）客户端（延迟初始化，幂等）"""
        # 如果已经初始化，直接返回
        if self.tat_client is not None:
            return
        
        try:
            from tencentcloud.tat.v20201028 import tat_client, models as tat_models
            self._tat_models = tat_models  # 保存引用供后续使用
        except ImportError as e:
            self.logger.warning(f"无法导入TAT SDK: {e}，下发指令功能将不可用")
            self.tat_client = None
            self._tat_models = None
            return
        
        cred = credential.Credential(self.secret_id, self.secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "tat.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        self.tat_client = tat_client.TatClient(cred, self.region, client_profile)
        self.logger.info(f"TAT客户端初始化成功，区域: {self.region}")
    
    def get_regions(self):
        """获取可用区域列表，用于区域选择或资源不足时的兜底重试。"""
        try:
            req = models.DescribeRegionsRequest()
            resp = self.client.DescribeRegions(req)
            regions = [{"Region": r.Region, "RegionName": r.RegionName, "RegionState": r.RegionState} for r in resp.RegionSet]
            self.logger.info(f"获取到{len(regions)}个可用区域")
            return regions
        except Exception as e:
            raise
    
    def get_type_configs(self, zone, cpu, memory, exact_match):
        """
        获取实例机型配置列表。

        - exact_match=True：仅返回 CPU/内存完全匹配的机型。
        - exact_match=False：返回不低于指定规格的机型，并按“距离”排序，首项最接近。
        """
        try:
            req = models.DescribeInstanceTypeConfigsRequest()
            if zone:
                # 如指定可用区，则过滤该可用区下的机型
                f = models.Filter()
                f.Name = "zone"
                f.Values = [zone]
                req.Filters = [f]
            
            resp = self.client.DescribeInstanceTypeConfigs(req)
            configs = []
            for c in resp.InstanceTypeConfigSet:
                if exact_match:
                    if cpu and c.CPU != cpu:
                        continue
                    if memory and c.Memory != memory:
                        continue
                else:
                    if cpu and c.CPU < cpu:
                        continue
                    if memory and c.Memory < memory:
                        continue
                configs.append({"InstanceType": c.InstanceType, "CPU": c.CPU, "Memory": c.Memory, "Zone": c.Zone, "InstanceFamily": c.InstanceFamily})
            
            if not exact_match and cpu and memory and configs:
                # 以“距离”排序，保证最接近的规格排在前面
                configs.sort(key=lambda x: (x["CPU"] - cpu) ** 2 + (x["Memory"] - memory) ** 2)
            
            self.logger.info(f"获取到{len(configs)}个实例机型配置")
            return configs
        except Exception as e:
            raise
    
    def get_zones(self, region):
        """获取指定区域的可用区列表，必要时切换客户端区域。"""
        try:
            target_region = region or self.region
            if target_region != self.region:
                self._init_client(target_region)
            
            req = models.DescribeZonesRequest()
            resp = self.client.DescribeZones(req)
            zones = []
            for z in resp.ZoneSet:
                z_region = getattr(z, 'Region', None)
                if z_region and z_region != target_region:
                    continue
                zones.append({"Zone": z.Zone, "ZoneName": z.ZoneName, "ZoneState": z.ZoneState, "Region": z_region or target_region})
            
            self.logger.info(f"获取到{len(zones)}个可用区（区域: {target_region}）")
            return zones
        except Exception as e:
            raise
    
    def get_images(self, image_type, limit=100):
        """获取镜像列表（公共/私有/共享/市场），支持限制返回条数。"""
        try:
            req = models.DescribeImagesRequest()
            req.Limit = limit
            # 过滤镜像类型
            f = models.Filter()
            f.Name = "image-type"
            f.Values = [image_type]
            req.Filters = [f]
            
            resp = self.client.DescribeImages(req)
            images = [{"ImageId": img.ImageId, "ImageName": img.ImageName, "ImageType": img.ImageType, "Platform": img.Platform, "CreatedTime": img.CreatedTime} for img in resp.ImageSet]
            self.logger.info(f"获取到{len(images)}个镜像")
            return images
        except Exception as e:
            raise
    
    def get_price(self, cpu, memory, region, image_id, zone, storage_size, bandwidth, disk_type="CLOUD_PREMIUM", bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):
        """
        查询实例价格（按量计费）。

        - 未指定可用区时，会取区域首个可用区。
        - 若请求规格不可用，使用最接近的规格并记录日志，避免直接报错。
        """
        try:
            if region != self.region:
                self._init_client(region)
            
            if not zone:
                zones = self.get_zones(region)
                if zones:
                    zone = zones[0]["Zone"]
                else:
                    raise ValueError(f"区域{region}没有可用区")
            
            configs = self.get_type_configs(zone, cpu, memory, False)
            if not configs:
                raise ValueError(f"在可用区{zone}中找不到{cpu}核{memory}G的实例机型配置")
            
            instance_type = configs[0]["InstanceType"]
            actual_cpu = configs[0]["CPU"]
            actual_memory = configs[0]["Memory"]
            if actual_cpu != cpu or actual_memory != memory:
                self.logger.info(f"使用最接近的配置: {actual_cpu}核{actual_memory}G (请求: {cpu}核{memory}G)")
            
            req = models.InquiryPriceRunInstancesRequest()
            # 显式设定按小时后付费，避免默认值差异
            req.InstanceChargeType = "POSTPAID_BY_HOUR"
            req.InstanceCount = 1
            req.InstanceType = instance_type
            req.ImageId = image_id
            req.SystemDisk = models.SystemDisk()
            req.SystemDisk.DiskSize = storage_size or 50
            req.SystemDisk.DiskType = disk_type or "CLOUD_PREMIUM"
            req.Placement = models.Placement()
            req.Placement.Zone = zone
            
            if bandwidth > 0:
                req.InternetAccessible = models.InternetAccessible()
                req.InternetAccessible.PublicIpAssigned = True
                req.InternetAccessible.InternetChargeType = bandwidth_charge or "TRAFFIC_POSTPAID_BY_HOUR"
                req.InternetAccessible.InternetMaxBandwidthOut = bandwidth
            
            resp = self.client.InquiryPriceRunInstances(req)
            price_info = {"cvm_price": "0", "cvm_unit": "HOUR", "bandwidth_price": "0", "bandwidth_unit": "GB"}
            
            if hasattr(resp, 'Price') and resp.Price:
                if hasattr(resp.Price, 'InstancePrice') and resp.Price.InstancePrice:
                    price_info["cvm_price"] = str(resp.Price.InstancePrice.UnitPrice)
                    price_info["cvm_unit"] = resp.Price.InstancePrice.ChargeUnit
                if hasattr(resp.Price, 'BandwidthPrice') and resp.Price.BandwidthPrice:
                    price_info["bandwidth_price"] = str(resp.Price.BandwidthPrice.UnitPrice)
                    price_info["bandwidth_unit"] = resp.Price.BandwidthPrice.ChargeUnit
            elif hasattr(resp, 'InstancePrice') and resp.InstancePrice:
                price_info["cvm_price"] = str(resp.InstancePrice.UnitPrice)
                price_info["cvm_unit"] = resp.InstancePrice.ChargeUnit
                if hasattr(resp, 'BandwidthPrice') and resp.BandwidthPrice:
                    price_info["bandwidth_price"] = str(resp.BandwidthPrice.UnitPrice)
                    price_info["bandwidth_unit"] = resp.BandwidthPrice.ChargeUnit
            
            cvm_price = price_info.get("cvm_price", "0")
            cvm_unit = price_info.get("cvm_unit", "HOUR")
            bandwidth_price = price_info.get("bandwidth_price", "0")
            bandwidth_unit = price_info.get("bandwidth_unit", "GB")
            self.logger.info(
                f"查询价格成功: 计算实例 {cvm_price}/{cvm_unit}，带宽 {bandwidth_price}/{bandwidth_unit}"
            )
            return price_info
        except Exception as e:
            raise
    
    def create(self, cpu, memory, region, password, image_id, instance_name, zone, count, system_disk_type="CLOUD_PREMIUM", system_disk_size=50, bandwidth=10, bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):
        """
        创建实例（按量计费）。

        - 镜像/可用区缺省时自动选择（公共镜像首个、区域首个可用区）。
        - 若指定规格在当前区域不足，后续会触发区域兜底重试。
        """
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            raise ValueError(f"密码验证失败: {error_msg}")
        
        try:
            warnings = []
            if region != self.region:
                self._init_client(region)
            
            # 验证zone是否属于当前region，如果不匹配则自动选择
            if zone:
                zones = self.get_zones(region)
                zone_list = [z.get("Zone") for z in zones or []]
                if zone not in zone_list:
                    warn_msg = f"配置的可用区 {zone} 不属于区域 {region}，已自动选择该区域的第一个可用区"
                    self.logger.warning(warn_msg)
                    warnings.append(warn_msg)
                    zone = None
            
            if not zone:
                zones = self.get_zones(region)
                if zones:
                    zone = zones[0]["Zone"]
                else:
                    raise ValueError(f"区域{region}没有可用区")
            
            if not image_id:
                images = self.get_images("PUBLIC_IMAGE")
                if images:
                    image_id = images[0]["ImageId"]
                else:
                    raise ValueError("无法获取可用镜像")
            
            configs = self.get_type_configs(zone, cpu, memory, False)
            if not configs:
                raise ValueError(f"在可用区{zone}中找不到{cpu}核{memory}G的实例机型配置")
            
            instance_type = configs[0]["InstanceType"]
            actual_cpu = configs[0]["CPU"]
            actual_memory = configs[0]["Memory"]
            if actual_cpu != cpu or actual_memory != memory:
                self.logger.info(f"使用最接近的配置: {actual_cpu}核{actual_memory}G (请求: {cpu}核{memory}G)")
            
            req = models.RunInstancesRequest()
            req.InstanceChargeType = "POSTPAID_BY_HOUR"
            req.InstanceType = instance_type
            req.ImageId = image_id
            req.Placement = models.Placement()
            req.Placement.Zone = zone
            req.SystemDisk = models.SystemDisk()
            req.SystemDisk.DiskType = system_disk_type or "CLOUD_PREMIUM"
            req.SystemDisk.DiskSize = system_disk_size or 50
            login_settings = models.LoginSettings()
            login_settings.Password = password
            req.LoginSettings = login_settings
            req.InstanceName = instance_name or f"CVM-{cpu}C{memory}G"
            req.InstanceCount = count
            req.InternetAccessible = models.InternetAccessible()
            req.InternetAccessible.PublicIpAssigned = True
            req.InternetAccessible.InternetChargeType = bandwidth_charge or "TRAFFIC_POSTPAID_BY_HOUR"
            req.InternetAccessible.InternetMaxBandwidthOut = bandwidth or 0
            
            self.logger.info(f"调用RunInstances API: 区域={region}, 可用区={zone}, 镜像={image_id}, 机型={instance_type}, 数量={count}, 磁盘类型={system_disk_type}")
            
            # 尝试创建实例，如果磁盘类型不支持则自动回退
            # 支持的磁盘类型：CLOUD_SSD, CLOUD_PREMIUM, CLOUD_BSSD, CLOUD_HSSD
            resp = None
            original_error = None
            tried_types = [system_disk_type]  # 记录已尝试的类型
            
            try:
                resp = self.client.RunInstances(req)
            except Exception as e:
                original_error = e
                error_str = str(e)
                # 检查是否是磁盘类型不支持的错误（错误码19045或错误信息包含"云硬盘类型"）
                is_disk_type_error = ("19045" in error_str or 
                                     "云硬盘类型" in error_str or 
                                     "云服务器不支持所需云硬盘类型" in error_str or
                                     ("InvalidParameter" in error_str and "disk" in error_str.lower()))
                
                if is_disk_type_error:
                    # 按优先级尝试其他支持的磁盘类型
                    # 优先级：CLOUD_PREMIUM（最通用）> CLOUD_SSD > CLOUD_BSSD > CLOUD_HSSD
                    fallback_types = ["CLOUD_PREMIUM", "CLOUD_SSD", "CLOUD_BSSD", "CLOUD_HSSD"]
                    # 排除已尝试的类型
                    fallback_types = [t for t in fallback_types if t not in tried_types]
                    
                    for fallback_type in fallback_types:
                        try:
                            warn_msg = f"磁盘类型 {tried_types[-1]} 在当前区域/可用区不支持，已尝试 {fallback_type}"
                            self.logger.warning(warn_msg)
                            warnings.append(warn_msg)
                            req.SystemDisk.DiskType = fallback_type
                            resp = self.client.RunInstances(req)
                            self.logger.info(f"成功使用磁盘类型 {fallback_type} 创建实例")
                            break
                        except Exception as e2:
                            tried_types.append(fallback_type)
                            if fallback_type == fallback_types[-1]:
                                # 所有类型都失败，抛出原始错误
                                self.logger.error(f"所有磁盘类型都尝试失败: {tried_types}")
                                raise original_error
                            continue
                else:
                    # 不是磁盘类型错误，直接抛出
                    raise
            
            if resp and resp.InstanceIdSet:
                instance_ids = list(resp.InstanceIdSet)
                self.logger.info(f"RunInstances API调用成功: 返回{len(instance_ids)}个实例ID={instance_ids}, RequestId={resp.RequestId}")
                
                # 写入本地缓存，前端可直接读取
                try:
                    db = get_db()
                    instance_data = []
                    for iid in instance_ids:
                        instance_data.append({
                            "InstanceId": iid,
                            "InstanceName": req.InstanceName,
                            "InstanceState": "PENDING",
                            "Region": region,
                            "Zone": zone,
                            "ImageId": image_id,
                            "CPU": actual_cpu,
                            "Memory": actual_memory,
                            "InstanceType": instance_type,
                        })
                    db.upsert_instances(instance_data)
                    self.logger.info(f"已将{len(instance_ids)}个实例写入数据库: {instance_ids}")
                except Exception as db_err:
                    self.logger.error(f"写入实例到数据库失败: {db_err}")
                    raise
                
                result_payload = {
                    "InstanceIds": instance_ids,
                    "Region": region,
                    "Zone": zone,
                    "Status": "PENDING",
                    "Warnings": warnings,
                }
                if count == 1:
                    result_payload["InstanceId"] = instance_ids[0]
                    return result_payload
                result_payload["Count"] = len(instance_ids)
                return result_payload
            else:
                self.logger.error("RunInstances API调用失败: 未返回实例ID")
                raise ValueError("实例创建失败，未返回实例ID")
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"创建实例失败: 区域={region}, 可用区={zone}, 错误={error_msg}")
            if "资源不足" in error_msg or "sold out" in error_msg.lower() or "ResourceInsufficient" in error_msg:
                self.logger.warning(f"区域{region}资源不足，尝试其他区域")
                return self._create_fallback(cpu, memory, region, password, image_id, instance_name)
            raise
    
    def _create_fallback(self, cpu, memory, preferred_region, password, image_id, instance_name):
        """资源不足时轮询其他区域尝试创建，全部失败则报错。"""
        self.logger.info(f"区域{preferred_region}资源不足，尝试其他区域...")
        regions = self.get_regions()
        for r_info in regions:
            r = r_info["Region"]
            if r == preferred_region:
                continue
            try:
                self.logger.info(f"尝试在区域{r}({get_region_name(r)})创建实例...")
                return self.create(cpu, memory, r, password, image_id, instance_name, None, 1)
            except Exception as e:
                self.logger.warning(f"区域{r}创建失败: {str(e)}")
                continue
        raise ValueError("所有区域都无法创建实例")
    
    def _describe_instances(self, region, instance_ids=None, offset=0, limit=100):
        """单次请求 DescribeInstances，支持传入 offset/limit 或指定 ID 列表。"""
        req = models.DescribeInstancesRequest()
        req.Limit = limit
        if offset:
            req.Offset = offset
        if instance_ids:
            req.InstanceIds = instance_ids
        resp = self.client.DescribeInstances(req)
        return resp.InstanceSet

    def get_instances(self, region, instance_ids=None):
        """
        获取实例列表。

        - 若传入 region 且与当前不同，会临时切换客户端区域。
        - 补充默认密码字段，便于 UI 直接展示/复制。
        - 尝试从可用区前缀推断实例所属区域。
        """
        try:
            if region and region != self.region:
                self._init_client(region)
            # 支持分页/分片（每批最多100）
            all_instances = []
            if instance_ids:
                # 按 100 拆分 ID 查询
                chunk_size = 100
                for i in range(0, len(instance_ids), chunk_size):
                    batch_ids = instance_ids[i:i + chunk_size]
                    all_instances.extend(self._describe_instances(region, batch_ids))
            else:
                offset = 0
                limit = 100
                while True:
                    batch = self._describe_instances(region, None, offset, limit)
                    if not batch:
                        break
                    all_instances.extend(batch)
                    if len(batch) < limit:
                        break
                    offset += limit
            
            from config.config_manager import get_instance_config
            cfg = get_instance_config()
            saved_pwd = cfg.get("default_password", "")  # 统一回填 UI 显示用密码
            
            instances = []
            for i in all_instances:
                placement = i.Placement
                zone = placement.Zone if placement else ""
                instance_region = self.region
                if zone:
                    for r in ["ap-beijing", "ap-shanghai", "ap-guangzhou", "ap-chengdu", "ap-chongqing", "ap-nanjing", "ap-shanghai-fsi", "ap-shenzhen-fsi", "ap-beijing-fsi", "ap-hongkong", "ap-singapore", "ap-mumbai", "ap-seoul", "ap-bangkok", "ap-tokyo", "na-siliconvalley", "na-ashburn", "na-toronto", "sa-saopaulo", "eu-frankfurt"]:
                        if zone.startswith(r):
                            instance_region = r
                            break
                
                # 公网优先，其次私网，缺省给空串
                public_ips = getattr(i, "PublicIpAddresses", []) or []
                private_ips = getattr(i, "PrivateIpAddresses", []) or []
                ip = public_ips[0] if public_ips else (private_ips[0] if private_ips else "")
                
                instances.append({
                    "InstanceId": i.InstanceId,
                    "InstanceName": i.InstanceName,
                    "InstanceState": i.InstanceState,
                    "InstanceType": i.InstanceType,
                    "CPU": i.CPU,
                    "Memory": i.Memory,
                    "Zone": zone,
                    "Region": instance_region,
                    "CreatedTime": i.CreatedTime,
                    "ExpiredTime": i.ExpiredTime,
                    "Platform": getattr(i, 'Platform', ''),
                    # 兼容缓存逻辑：优先写入公网/私网数组，DB 层会取首个
                    "PublicIpAddresses": public_ips,
                    "PrivateIpAddresses": private_ips,
                    "IpAddress": ip,
                    "Password": saved_pwd
                })
            
            try:
                db = get_db()
                # 先更新/插入API返回的实例（upsert会自动更新status，去掉-1标识）
                db.upsert_instances(instances)
                # 只有在全量查询（不是按ID查询）时才处理缺失记录
                # 标记不在API返回列表中的实例为-1
                if not instance_ids:
                    valid_ids = [ins["InstanceId"] for ins in instances]
                    db.soft_delete_missing(valid_ids)
            except Exception as db_err:
                self.logger.warning(f"写入实例缓存失败: {db_err}")
            
            self.logger.info(f"获取到{len(instances)}个实例")
            return instances
        except Exception as e:
            raise
    
    def start(self, instance_ids, skip_db_update=False):
        """
        批量启动实例。

        Args:
            instance_ids: 实例 ID 列表
            skip_db_update: 如果为True，跳过数据库更新（由调用者控制）
        """
        prev = None
        try:
            if isinstance(instance_ids, str):
                instance_ids = [instance_ids]
            
            # 如果不跳过数据库更新，则保存原始状态并标记为STARTING
            if not skip_db_update:
                db = get_db()
                prev = db.get_instances(instance_ids)
                for iid in instance_ids:
                    db.update_instance_status(iid, "STARTING")
            
            # 调用API启动实例
            req = models.StartInstancesRequest()
            req.InstanceIds = instance_ids
            resp = self.client.StartInstances(req)
            self.logger.info(f"批量启动{len(instance_ids)}个实例: {instance_ids}")
            return {"RequestId": resp.RequestId, "InstanceIds": instance_ids}
        except Exception as e:
            # 如果API调用失败且不是跳过数据库更新模式，则回滚状态
            if not skip_db_update:
                try:
                    db = get_db()
                    for row in prev or []:
                        db.update_instance_status(row.get("instance_id"), row.get("status") or None)
                except Exception:
                    pass
            raise
    
    def stop(self, instance_ids, force, skip_db_update=False):
        """
        批量停止实例。

        Args:
            instance_ids: 实例 ID 列表
            force: 是否强制关机（True 会强制，False 优雅停机）
            skip_db_update: 如果为True，跳过数据库更新（由调用者控制）
        """
        prev = None
        try:
            if isinstance(instance_ids, str):
                instance_ids = [instance_ids]
            
            # 如果不跳过数据库更新，则保存原始状态并标记为STOPPING
            if not skip_db_update:
                db = get_db()
                prev = db.get_instances(instance_ids)
                for iid in instance_ids:
                    db.update_instance_status(iid, "STOPPING")
            
            # 调用API停止实例
            req = models.StopInstancesRequest()
            req.InstanceIds = instance_ids
            req.ForceStop = force
            resp = self.client.StopInstances(req)
            self.logger.info(f"批量停止{len(instance_ids)}个实例: {instance_ids}")
            return {"RequestId": resp.RequestId, "InstanceIds": instance_ids}
        except Exception as e:
            # 如果API调用失败且不是跳过数据库更新模式，则回滚状态
            if not skip_db_update:
                try:
                    db = get_db()
                    for row in prev or []:
                        db.update_instance_status(row.get("instance_id"), row.get("status") or None)
                except Exception:
                    pass
            raise
    
    def reset_pwd(self, instance_ids, password, auto_start=True):
        """
        批量重置实例密码
        
        Args:
            instance_ids: 实例ID列表
            password: 新密码
            auto_start: 是否在重置密码后自动开机（默认True）
        """
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            raise ValueError(f"密码验证失败: {error_msg}")
        
        try:
            instances = self.get_instances(None)  # 查询当前区域全部实例，判断运行状态
            running_instance_ids = []
            has_running = False
            for instance in instances:
                instance_id = instance.get("InstanceId")
                if instance_id in instance_ids and instance.get("InstanceState") == "RUNNING":
                    has_running = True
                    running_instance_ids.append(instance_id)
            
            req = models.ResetInstancesPasswordRequest()
            req.InstanceIds = instance_ids
            req.Password = password
            if has_running:
                req.ForceStop = True  # 运行中实例需先关机才能重置密码
                self.logger.info(f"检测到运行中的实例，使用强制关机方式重置密码")
            
            resp = self.client.ResetInstancesPassword(req)
            self.logger.info(f"批量重置{len(instance_ids)}个实例的密码")
            
            # 如果启用自动开机，且原本有运行中的实例，则自动开机
            if auto_start and running_instance_ids:
                # 等待一小段时间，让密码重置操作完成
                time.sleep(2)
                try:
                    self.start(running_instance_ids)
                    self.logger.info(f"已自动开机{len(running_instance_ids)}个实例")
                except Exception as e:
                    self.logger.warning(f"自动开机失败: {str(e)}，请手动开机")
            
            return {"RequestId": resp.RequestId, "InstanceIds": instance_ids}
        except Exception as e:
            raise
    
    def terminate(self, instance_ids, skip_db_update=False):
        """
        销毁实例（按量计费），支持单个或列表形式传入。
        
        Args:
            instance_ids: 实例ID列表或单个ID
            skip_db_update: 如果为True，跳过数据库更新（由调用者控制）
        """
        prev = None
        try:
            if isinstance(instance_ids, str):
                instance_ids = [instance_ids]
            
            # 如果不跳过数据库更新，则保存原始状态并标记为-1
            if not skip_db_update:
                db = get_db()
                prev = db.get_instances(instance_ids)
                for iid in instance_ids:
                    db.update_instance_status(iid, "-1")
            
            # 调用API销毁实例
            req = models.TerminateInstancesRequest()
            req.InstanceIds = instance_ids
            resp = self.client.TerminateInstances(req)
            self.logger.info(f"销毁{len(instance_ids)}个实例: {instance_ids}")
            return {"RequestId": resp.RequestId, "InstanceIds": instance_ids}
        except Exception as e:
            # 如果API调用失败且不是跳过数据库更新模式，则回滚状态
            if not skip_db_update:
                try:
                    db = get_db()
                    for row in prev or []:
                        db.update_instance_status(row.get("instance_id"), row.get("status") or None)
                except Exception:
                    pass
            raise
    
    def create_image(self, instance_id, image_name, image_desc):
        """创建自定义镜像，将实例快照化为可复用镜像。"""
        try:
            req = models.CreateImageRequest()
            req.InstanceId = instance_id
            req.ImageName = image_name
            if image_desc:
                req.ImageDescription = image_desc
            resp = self.client.CreateImage(req)
            self.logger.info(f"创建自定义镜像: {resp.ImageId}")
            return {"ImageId": resp.ImageId, "RequestId": resp.RequestId}
        except Exception as e:
            raise
    
    def list_images(self):
        """获取自定义镜像列表"""
        return self.get_images("PRIVATE_IMAGE")
    
    def run_command(self, instance_ids, command_content, command_type="SHELL", working_directory=None, timeout=60, username=None, command_name=None, description=None):
        """
        执行命令（下发指令）
        
        根据API文档要求：
        - 实例必须处于 RUNNING 状态
        - 实例需要处于 VPC 网络
        - 实例必须安装 TAT Agent 且 Agent 在线
        
        Args:
            instance_ids: 实例ID列表（上限200）
            command_content: 命令内容（原始字符串，会自动Base64编码，长度不超过64KB）
            command_type: 命令类型，SHELL（Linux）或POWERSHELL/BAT（Windows），默认SHELL
            working_directory: 工作目录，SHELL默认为/root，POWERSHELL默认为C:\Program Files\qcloud\tat_agent\workdir
            timeout: 超时时间（秒），默认60，取值范围[1, 86400]
            username: 执行用户，默认root（Linux）或System（Windows）
            command_name: 命令名称（可选），仅支持中文、英文、数字、下划线、分隔符"-"、小数点，最大长度60字节
            description: 命令描述（可选），不超过120字符
        
        Returns:
            dict: 包含CommandId、InvocationId和RequestId
        """
        # 延迟初始化TAT客户端
        if not self.tat_client:
            self._init_tat_client()
            if not self.tat_client:
                raise RuntimeError("TAT客户端未初始化，请检查TAT SDK是否正确安装")
        
        import base64
        
        try:
            # Base64编码命令内容
            command_base64 = base64.b64encode(command_content.encode('utf-8')).decode('utf-8')
            
            req = self._tat_models.RunCommandRequest()
            req.Content = command_base64
            req.InstanceIds = instance_ids
            req.CommandType = command_type
            req.Timeout = timeout
            req.SaveCommand = False  # 不保存命令（根据API文档，默认为false）
            
            # 可选参数：命令名称和描述
            if command_name:
                req.CommandName = command_name
            if description:
                req.Description = description
            
            # 工作目录：如果未指定，使用API文档中的默认值
            if working_directory:
                req.WorkingDirectory = working_directory
            else:
                # 根据命令类型设置默认工作目录（符合API文档）
                if command_type == "SHELL":
                    req.WorkingDirectory = "/root"
                elif command_type in ["POWERSHELL", "BAT"]:
                    req.WorkingDirectory = r"C:\Program Files\qcloud\tat_agent\workdir"
            
            if username:
                req.Username = username
            
            resp = self.tat_client.RunCommand(req)
            self.logger.info(f"执行命令成功: InvocationId={resp.InvocationId}, CommandId={resp.CommandId}")
            return {
                "CommandId": resp.CommandId,
                "InvocationId": resp.InvocationId,
                "RequestId": resp.RequestId
            }
        except Exception as e:
            self.logger.error(f"执行命令失败: {e}")
            # 将技术性错误信息转换为更友好的提示（根据API文档的错误码）
            error_str = str(e)
            import re
            
            # 提取实例ID（如果存在）
            instance_match = re.search(r'instance[`\s]+([a-z0-9-]+)', error_str, re.IGNORECASE)
            instance_id = instance_match.group(1) if instance_match else "指定"
            
            # 根据API文档的错误码提供友好提示
            if "AgentNotInstalled" in error_str or "agent not installed" in error_str.lower():
                raise RuntimeError(
                    f"实例 {instance_id} 未安装 TAT Agent。\n\n"
                    "请先在实例上安装 TAT Agent 后才能使用下发指令功能。\n\n"
                    "安装方法：\n"
                    "1. Linux: 执行安装脚本\n"
                    "   wget https://tat-gz-1258344699.cos.ap-guangzhou.myqcloud.com/tat_agent_install.sh\n"
                    "   bash tat_agent_install.sh\n"
                    "2. Windows: 在腾讯云控制台下载并安装 TAT Agent"
                )
            elif "AgentStatusNotOnline" in error_str or "agent.*not.*online" in error_str.lower():
                raise RuntimeError(
                    f"实例 {instance_id} 的 TAT Agent 不在线。\n\n"
                    "请确保：\n"
                    "1. TAT Agent 已正确安装\n"
                    "2. Agent 服务正在运行\n"
                    "3. 实例网络连接正常"
                )
            elif "InstanceStateNotRunning" in error_str or "instance.*not.*running" in error_str.lower():
                raise RuntimeError(
                    f"实例 {instance_id} 未处于运行中状态。\n\n"
                    "根据API文档要求，执行命令时实例必须处于 RUNNING 状态。\n"
                    "请先启动实例后再尝试下发指令。"
                )
            elif "InvalidInstanceId" in error_str:
                raise RuntimeError(
                    f"实例ID无效：{instance_id}\n\n"
                    "请检查实例ID是否正确，或实例是否存在于当前区域。"
                )
            raise
    
    def describe_invocation_tasks(self, invocation_id=None, invocation_task_ids=None, instance_id=None, limit=20, offset=0):
        """
        查询执行任务详情
        
        根据API文档：
        - 参数不支持同时指定 InvocationTaskIds 和 Filters
        - 每次请求的 Filters 上限为10，Filter.Values 上限为5
        - InvocationTaskIds 每次请求上限为100
        
        Args:
            invocation_id: 执行活动ID（通过过滤器查询）
            invocation_task_ids: 执行任务ID列表（每次请求上限100，与Filters互斥）
            instance_id: 实例ID（通过过滤器查询，与InvocationTaskIds互斥）
            limit: 返回数量，默认20，最大值为100
            offset: 偏移量，默认0
        
        Returns:
            dict: 包含TotalCount、InvocationTaskSet和RequestId
                InvocationTaskSet中每个任务包含：
                - InvocationTaskId: 执行任务ID
                - InvocationId: 执行活动ID
                - InstanceId: 实例ID
                - TaskStatus: 任务状态（PENDING/RUNNING/SUCCESS/FAILED/TIMEOUT等）
                - CommandId: 命令ID
                - TaskResult: 任务结果（ExitCode、Output、ExecStartTime、ExecEndTime等）
                - ErrorInfo: 错误信息
        """
        # 延迟初始化TAT客户端
        if not self.tat_client:
            self._init_tat_client()
            if not self.tat_client:
                raise RuntimeError("TAT客户端未初始化，请检查TAT SDK是否正确安装")
        
        try:
            req = self._tat_models.DescribeInvocationTasksRequest()
            req.Limit = limit
            req.Offset = offset
            req.HideOutput = False  # 显示输出
            
            if invocation_task_ids:
                req.InvocationTaskIds = invocation_task_ids
            elif invocation_id or instance_id:
                # 使用过滤器
                filters = []
                if invocation_id:
                    filter_item = self._tat_models.Filter()
                    filter_item.Name = "invocation-id"
                    filter_item.Values = [invocation_id]
                    filters.append(filter_item)
                if instance_id:
                    filter_item = self._tat_models.Filter()
                    filter_item.Name = "instance-id"
                    filter_item.Values = [instance_id]
                    filters.append(filter_item)
                req.Filters = filters
            
            resp = self.tat_client.DescribeInvocationTasks(req)
            self.logger.info(f"查询执行任务成功: TotalCount={resp.TotalCount}")
            return {
                "TotalCount": resp.TotalCount,
                "InvocationTaskSet": [
                    {
                        "InvocationTaskId": task.InvocationTaskId,
                        "InvocationId": task.InvocationId,
                        "InstanceId": task.InstanceId,
                        "TaskStatus": task.TaskStatus,
                        "CommandId": task.CommandId,
                        "StartTime": task.StartTime,
                        "EndTime": task.EndTime,
                        "CreatedTime": task.CreatedTime,
                        "UpdatedTime": task.UpdatedTime,
                        "TaskResult": {
                            "ExitCode": task.TaskResult.ExitCode if task.TaskResult else None,
                            "Output": task.TaskResult.Output if task.TaskResult else None,
                            "ExecStartTime": task.TaskResult.ExecStartTime if task.TaskResult else None,
                            "ExecEndTime": task.TaskResult.ExecEndTime if task.TaskResult else None,
                        } if task.TaskResult else None,
                        "ErrorInfo": task.ErrorInfo if hasattr(task, 'ErrorInfo') else ""
                    }
                    for task in resp.InvocationTaskSet
                ],
                "RequestId": resp.RequestId
            }
        except Exception as e:
            self.logger.error(f"查询执行任务失败: {e}")
            raise


if __name__ == "__main__":
    print("错误：此文件是模块文件，不应直接运行。")
    print("请使用以下命令启动应用程序：")
    print("  python main.py")
    exit(1)
