import freighter
import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="freighter",
    version=freighter.__version__,
    author=freighter.__author__,
    description="Kai's GameCube modding library enabling C/C++ code injection into .dol executables.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kai13xd/Freighter",
    project_urls={
        "Issues": "https://github.com/kai13xd/Freighter/issues",
    },
    license="MIT License",
    author_email="akaisekai13@gmail.com",
    packages=setuptools.find_packages(),
    include_package_data=True,
    classifiers=[
        "Topic :: Games/Entertainment",
        "Topic :: Software Development :: Compilers",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: C",
        "Programming Language :: C++",
        "License :: OSI Approved :: MIT License",
        "Environment :: Console",
        "Operating System :: Microsoft :: Windows",
    ],
    install_requires=("colorama", "dolreader", "pyelftools", "geckolibs"),
    python_requires=">=3.9",
)
