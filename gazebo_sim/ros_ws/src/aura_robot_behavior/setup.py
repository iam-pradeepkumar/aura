from setuptools import setup

package_name = "aura_robot_behavior"

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
            "behavior_node = aura_robot_behavior.behavior_node:main",
        ],
    },
)
