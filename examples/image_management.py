"""
镜像管理示例
"""
from core.cvm_manager import CVMManager

if __name__ == "__main__":
    manager = CVMManager(None, None, None)
    
    print("获取公共镜像列表...")
    public_images = manager.get_images("PUBLIC_IMAGE")
    print(f"共有{len(public_images)}个公共镜像")
    for img in public_images[:5]:
        print(f"  - {img['ImageName']} ({img['ImageId']})")
    
    print("\n获取自定义镜像列表...")
    custom_images = manager.list_images()
    print(f"共有{len(custom_images)}个自定义镜像")
    for img in custom_images:
        print(f"  - {img['ImageName']} ({img['ImageId']})")
