#!/usr/bin/env python
"""
Telegram Configuration for MrBets.ai

Contains all Telegram-related settings including bot tokens, channel IDs,
and other Telegram service configurations.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram Bot Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Telegram Channels (for different languages)
TELEGRAM_CHANNEL_EN = os.getenv("TELEGRAM_CHANNEL_EN")   # @MrBetsAI_EN
TELEGRAM_CHANNEL_RU = os.getenv("TELEGRAM_CHANNEL_RU")   # @MrBetsAI_RU
TELEGRAM_CHANNEL_UZ = os.getenv("TELEGRAM_CHANNEL_UZ")   # @MrBetsAI_UZ
TELEGRAM_CHANNEL_AR = os.getenv("TELEGRAM_CHANNEL_AR")   # @MrBetsAI_AR

# Admin Settings
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID")  # для алертов мониторинга

# Content Publishing Settings
CONTENT_QUALITY_THRESHOLD = int(os.getenv("CONTENT_QUALITY_THRESHOLD", "7"))
BREAKING_NEWS_COOLDOWN = int(os.getenv("BREAKING_NEWS_COOLDOWN", "300"))  # секунды

# Language mapping for content routing
CHANNEL_LANGUAGE_MAP = {
    TELEGRAM_CHANNEL_EN: "EN",
    TELEGRAM_CHANNEL_RU: "RU", 
    TELEGRAM_CHANNEL_UZ: "UZ",
    TELEGRAM_CHANNEL_AR: "AR"
}

# Reverse mapping for easy lookup
LANGUAGE_CHANNEL_MAP = {v: k for k, v in CHANNEL_LANGUAGE_MAP.items()}

# Content type templates
CONTENT_TEMPLATES = {
    "full_prediction": {
        "EN": "🎯 **Match Prediction**\n\n{content}\n\n⚽ Confidence: {confidence}%",
        "RU": "🎯 **Прогноз на матч**\n\n{content}\n\n⚽ Уверенность: {confidence}%",
        "UZ": "🎯 **O'yin prognozi**\n\n{content}\n\n⚽ Ishonch: {confidence}%",
        "AR": "🎯 **توقع المباراة**\n\n{content}\n\n⚽ الثقة: {confidence}%"
    },
    "patch": {
        "EN": "🚨 **URGENT UPDATE**\n\n{content}",
        "RU": "🚨 **СРОЧНОЕ ОБНОВЛЕНИЕ**\n\n{content}",
        "UZ": "🚨 **SHOSHILINCH YANGILIK**\n\n{content}",
        "AR": "🚨 **تحديث عاجل**\n\n{content}"
    },
    "breaking_news": {
        "EN": "🔥 **Breaking News**\n\n{content}",
        "RU": "🔥 **Срочные новости**\n\n{content}",
        "UZ": "🔥 **Shoshilinch yangiliklar**\n\n{content}",
        "AR": "🔥 **أخبار عاجلة**\n\n{content}"
    }
}

# Validation
def validate_telegram_config():
    """Validate that all required Telegram settings are present"""
    required_vars = [
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        ("TELEGRAM_CHANNEL_EN", TELEGRAM_CHANNEL_EN),
        ("TELEGRAM_ADMIN_CHAT_ID", TELEGRAM_ADMIN_CHAT_ID)
    ]
    
    missing = []
    for var_name, var_value in required_vars:
        if not var_value:
            missing.append(var_name)
    
    if missing:
        raise ValueError(f"Missing required Telegram configuration: {', '.join(missing)}")
    
    return True

# Utility functions
def get_channel_for_language(language: str) -> str:
    """Get channel ID for a specific language"""
    return LANGUAGE_CHANNEL_MAP.get(language.upper())

def get_language_for_channel(channel: str) -> str:
    """Get language for a specific channel"""
    return CHANNEL_LANGUAGE_MAP.get(channel)

def format_content(content_type: str, language: str, content: str, **kwargs) -> str:
    """Format content using templates"""
    template = CONTENT_TEMPLATES.get(content_type, {}).get(language.upper())
    if not template:
        return content  # Fallback to raw content
    
    try:
        return template.format(content=content, **kwargs)
    except KeyError:
        return content  # Fallback if template variables missing

# Export all configuration
__all__ = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHANNEL_EN", 
    "TELEGRAM_CHANNEL_RU",
    "TELEGRAM_CHANNEL_UZ", 
    "TELEGRAM_CHANNEL_AR",
    "TELEGRAM_ADMIN_CHAT_ID",
    "CONTENT_QUALITY_THRESHOLD",
    "BREAKING_NEWS_COOLDOWN",
    "CHANNEL_LANGUAGE_MAP",
    "LANGUAGE_CHANNEL_MAP", 
    "CONTENT_TEMPLATES",
    "validate_telegram_config",
    "get_channel_for_language",
    "get_language_for_channel",
    "format_content"
] 