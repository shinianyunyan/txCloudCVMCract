"""
批量操作示例
"""
from core.cvm_manager import CVMManager

if __name__ == "__main__":
    manager = CVMManager(None, None, None)
    instances = manager.get_instances(None)
    print(f"当前有{len(instances)}个实例")
    
    instance_ids = [inst["InstanceId"] for inst in instances[:3]]
    if not instance_ids:
        print("没有可操作的实例")
    else:
        print(f"\n批量启动{len(instance_ids)}个实例...")
        result = manager.start(instance_ids)
    print(f"操作结果: {result}")
