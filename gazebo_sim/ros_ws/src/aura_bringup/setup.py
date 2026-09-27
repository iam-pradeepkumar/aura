from setuptools import setup

package_name = "aura_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/mobile_mission.launch.py"]),
        ("share/" + package_name + "/worlds", ["../../worlds/disaster_zone.sdf"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="AURA",
    maintainer_email="aura@local",
    description="AURA mobile SAR bringup",
    license="MIT",
    entry_points={"console_scripts": []},
)
