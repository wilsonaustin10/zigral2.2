from setuptools import setup, find_packages

setup(
    name="lam",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "anthropic>=0.8.0",
        "playwright>=1.40.0",
        "pydantic>=2.5.2",
        "python-dotenv>=1.0.0",
        "pytest>=7.4.3",
        "pytest-asyncio>=0.21.1",
        "pytest-mock>=3.14.0",
        "pytest-cov>=6.0.0"
    ],
    python_requires=">=3.8",
) 