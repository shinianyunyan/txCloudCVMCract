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


if __name__ == "__main__":
    print("错误：此文件是模块文件，不应直接运行。")
    print("请使用以下命令启动应用程序：")
    print("  python main.py")
    exit(1)
