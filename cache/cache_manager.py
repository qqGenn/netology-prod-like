import os
import json
import time
from typing import Optional, Dict, Any

from core.log import logger

# Константа TTL (time-to-live) для кэша - 10 минут
CACHE_TTL_SECONDS = 10 * 60


class CacheManager:
    """Менеджер кэша для хранения ответов от LLM."""
    
    def __init__(self, cache_dir: str = "cache/data"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        logger.info(f"Инициализирован CacheManager с директорией: {cache_dir}")
    
    def _get_cache_file_path(self, key: str) -> str:
        """Получить путь к файлу кэша по ключу."""
        return os.path.join(self.cache_dir, f"{key}.json")
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Получить данные из кэша по ключу.
        
        Args:
            key: Хэш-ключ запроса
            
        Returns:
            Словарь с данными или None, если данные не найдены или истёк TTL
        """
        cache_file = self._get_cache_file_path(key)
        
        if not os.path.exists(cache_file):
            logger.info(f"cache_miss: Кэш-файл не найден: {cache_file}")
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Проверяем наличие метки времени
            if "timestamp" not in cache_data:
                logger.warning(f"В кэш-файле отсутствует timestamp: {cache_file}")
                self.delete(key)
                return None
            
            timestamp = cache_data["timestamp"]
            current_time = time.time()
            
            # Проверяем, не истёк ли TTL
            if current_time - timestamp > CACHE_TTL_SECONDS:
                logger.info(f"cache_miss: Кэш истёк для ключа: {key}")
                self.delete(key)
                return None
            
            # Удаляем метку времени из возвращаемых данных
            data = {k: v for k, v in cache_data.items() if k != "timestamp"}
            logger.info(f"cache_hit: Данные успешно прочитаны из кэша: {cache_file}")
            return data
            
        except Exception as e:
            logger.error(f"Ошибка при чтении кэша из {cache_file}: {e}")
            return None
    
    def set(self, key: str, data: Dict[str, Any]) -> bool:
        """
        Сохранить данные в кэш по ключу.
        
        Args:
            key: Хэш-ключ запроса
            data: Данные для сохранения
            
        Returns:
            True при успешной записи, False иначе
        """
        cache_file = self._get_cache_file_path(key)
        
        try:
            # Добавляем метку времени
            cache_data = {
                "timestamp": time.time(),
                **data
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Данные успешно записаны в кэш: {cache_file}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при записи в кэш {cache_file}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Удалить данные из кэша по ключу.
        
        Args:
            key: Хэш-ключ запроса
            
        Returns:
            True при успешном удалении, False иначе
        """
        cache_file = self._get_cache_file_path(key)
        
        if not os.path.exists(cache_file):
            logger.debug(f"Кэш-файл не найден для удаления: {cache_file}")
            return False
        
        try:
            os.remove(cache_file)
            logger.debug(f"Кэш-файл успешно удалён: {cache_file}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении кэша {cache_file}: {e}")
            return False
