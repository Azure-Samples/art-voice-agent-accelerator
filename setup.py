"""Setup configuration for the Real-Time Voice Agent package."""

from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [
        line.strip() for line in f if line.strip() and not line.startswith("#")
    ]

# Read long description from README
try:
    with open("README.md", "r", encoding="utf-8") as f:
        long_description = f.read()
except FileNotFoundError:
    long_description = "Real-time voice agent with Azure AI and Apps Service"

setup(
    name="gbb-ai-audio-agent",
    version="1.0.0",
    description="Real-time voice agent with Azure AI and Apps Service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Pablo Salvador, Jin Lee",
    author_email="pablosalvador11@gmail.com",
    url="https://github.com/pablosalvador10/gbb-ai-audio-agent",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "docs": [
            "mkdocs>=1.5.0",
            "mkdocs-material>=9.0.0",
            "mkdocstrings[python]>=0.20.0",
            "pymdown-extensions>=10.0.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications :: Telephony",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
    ],
    keywords="azure speech voice tts stt real-time audio ai and apps-services",
    project_urls={
        "Documentation": "https://pablosalvador10.github.io/gbb-ai-audio-agent/",
        "Source": "https://github.com/pablosalvador10/gbb-ai-audio-agent",
        "Tracker": "https://github.com/pablosalvador10/gbb-ai-audio-agent/issues",
    },
)
