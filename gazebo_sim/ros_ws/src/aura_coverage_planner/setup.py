from setuptools import setup

package_name = "aura_coverage_planner"

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
            "planner_node = aura_coverage_planner.planner_node:main",
        ],
    },
)
