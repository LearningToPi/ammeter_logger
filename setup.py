import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ammeter_logger",
    version="0.1.2",
    author="Thomas Dunteman",
    author_email="ammeter@learningtopi.com",
    description="Ammeter logging tool - used to receive from micropython serial connection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/learningtopi/ammeter_logger",
    project_urls={
        "Bug Tracker": "https://github.com/learningtopi/ammeter_logger/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    package_dir={"": "src"},
    packages=setuptools.find_packages(where="src"),
    python_requires=">=3.6",
    install_requires=[
        'pyserial>=3.5'
    ]
)
