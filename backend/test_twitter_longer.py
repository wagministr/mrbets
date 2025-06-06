#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from fetchers.twitter_fetcher import TwitterFetcher

async def test_longer_period():
    fetcher = TwitterFetcher()
    await fetcher.connect_redis()
    
    print('🔍 Тест с периодом 24 часа...')
    expert_tweets = await fetcher.fetch_expert_tweets(hours_back=24)
    print(f'📊 Найдено {len(expert_tweets)} экспертных твитов за 24 часа')
    
    if expert_tweets:
        print('📝 Примеры экспертных твитов:')
        for i, tweet in enumerate(expert_tweets[:5]):
            print(f'  {i+1}. @{tweet["author"]["username"]}: {tweet["text"][:100]}...')
            print(f'     Engagement: {tweet["engagement_score"]}, Reliability: {tweet["reliability_score"]}')
    
    print('\n🔍 Тест поиска по ключевым словам (6 часов)...')
    keyword_tweets = await fetcher.search_keyword_tweets(hours_back=6, max_results=20)
    print(f'📊 Найдено {len(keyword_tweets)} твитов по ключевым словам за 6 часов')
    
    if keyword_tweets:
        print('📝 Примеры твитов по ключевым словам:')
        for i, tweet in enumerate(keyword_tweets[:3]):
            print(f'  {i+1}. @{tweet["author"]["username"]}: {tweet["text"][:100]}...')
            print(f'     Хэштеги: {tweet["hashtags"]}')
    
    await fetcher.close()

if __name__ == "__main__":
    asyncio.run(test_longer_period()) 