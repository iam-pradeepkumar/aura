from setuptools import setup

package_name = "aura_fake_csi"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="AURA",
    license="MIT",
    entry_points={
        "console_scripts": [
            "fake_csi_node = aura_fake_csi.fake_csi_node:main",
        ],
    },
)
