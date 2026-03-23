"""
LLM服务 - 集成OpenAI/Azure OpenAI
"""
from typing import List, Dict, Any, Optional, AsyncGenerator
import openai
from openai import AsyncOpenAI

from app.core.config import settings


class LLMService:
    """LLM服务类"""
    
    def __init__(self):
        self.client = None
        self.init_error = None
        self._init_client()
    
    def _init_client(self):
        """初始化OpenAI客户端"""
        self.init_error = None
        if settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_KEY:
            # 使用Azure OpenAI
            self.client = AsyncOpenAI(
                api_key=settings.AZURE_OPENAI_KEY,
                base_url=f"{settings.AZURE_OPENAI_ENDPOINT}openai/deployments/",
                default_query={"api-version": settings.AZURE_OPENAI_VERSION},
            )
        elif settings.OPENAI_API_KEY:
            # 使用标准OpenAI
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        else:
            self.client = None
            self.init_error = "未配置OpenAI API密钥"

    def _ensure_client(self):
        """按需校验客户端初始化状态。"""
        if not self.client:
            if not self.init_error:
                self._init_client()
            raise RuntimeError(self.init_error or "LLM客户端未初始化")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        聊天补全
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度
            max_tokens: 最大token数
            stream: 是否流式输出
        
        Returns:
            响应结果
        """
        self._ensure_client()
        
        model = model or settings.OPENAI_MODEL
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
            )
            
            if stream:
                return response  # 返回异步生成器
            
            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
            }
        except Exception as e:
            raise RuntimeError(f"LLM调用失败: {str(e)}")
    
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天补全
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度
            max_tokens: 最大token数
        
        Yields:
            文本片段
        """
        self._ensure_client()
        
        model = model or settings.OPENAI_MODEL
        
        try:
            stream = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise RuntimeError(f"LLM流式调用失败: {str(e)}")
    
    async def create_embedding(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> List[float]:
        """
        创建文本嵌入向量
        
        Args:
            text: 输入文本
            model: 嵌入模型名称
        
        Returns:
            嵌入向量
        """
        self._ensure_client()
        
        model = model or settings.OPENAI_EMBEDDING_MODEL
        
        try:
            response = await self.client.embeddings.create(
                model=model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            raise RuntimeError(f"嵌入生成失败: {str(e)}")
    
    async def create_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """
        批量创建文本嵌入向量
        
        Args:
            texts: 输入文本列表
            model: 嵌入模型名称
        
        Returns:
            嵌入向量列表
        """
        self._ensure_client()
        
        model = model or settings.OPENAI_EMBEDDING_MODEL
        
        try:
            response = await self.client.embeddings.create(
                model=model,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            raise RuntimeError(f"批量嵌入生成失败: {str(e)}")


# 全局LLM服务实例
llm_service = LLMService()
