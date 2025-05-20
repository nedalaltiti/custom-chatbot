# """
# Integration module for connecting application components.

# This module provides:
# 1. Component registration and dependency injection
# 2. Proper sequencing of component initialization
# 3. Service lifecycle management
# 4. Integration between different modules and subsystems

# It serves as the central hub for component configuration and wiring.
# """

# import logging
# from typing import Dict, Any, Optional, Callable, TypeVar, Type, cast
# from functools import lru_cache

# from hrbot.config.settings import settings
# from hrbot.utils.error import ConfigError, ErrorSeverity
# from hrbot.infrastructure.vector_store import VectorStore
# from hrbot.services.gemini_service import GeminiService
# from hrbot.core.rag.engine import RAG

# logger = logging.getLogger(__name__)

# # Type for component constructor functions
# T = TypeVar('T')
# Constructor = Callable[[], T]

# # Registry of components by type
# _components: Dict[Type, Any] = {}
# _initialized = False


# async def initialize_application() -> None:
#     """
#     Initialize all application components in the correct order.
    
#     This ensures proper dependency resolution and initialization sequencing.
    
#     Raises:
#         ConfigError: If initialization fails
#     """
#     global _initialized
    
#     if _initialized:
#         logger.info("Application already initialized")
#         return
    
#     try:
#         logger.info("Initializing application components")
        
#         # Initialize services in dependency order
        
#         # 1. Initialize base services
#         logger.info("Initializing LLM service")
#         llm_service = GeminiService()
#         register_component(GeminiService, llm_service)
        
#         # 2. Initialize vector store
#         logger.info("Initializing vector store")
#         vector_store = VectorStore()
#         register_component(VectorStore, vector_store)
        
#         # 3. Initialize RAG core implementation
#         logger.info("Initializing RAG core")
#         rag_core = RAG(vector_store=vector_store, llm_provider=llm_service)
#         register_component(RAG, rag_core)
        
#         logger.info("Application components initialized successfully")
#         _initialized = True
        
#     except Exception as e:
#         logger.error(f"Error initializing application: {str(e)}")
#         raise ConfigError(
#             message=f"Application initialization failed: {str(e)}",
#             severity=ErrorSeverity.CRITICAL,
#             cause=e
#         )


# def register_component(component_type: Type[T], instance: T) -> None:
#     """
#     Register a component instance by type.
    
#     Args:
#         component_type: Type of the component
#         instance: Component instance
#     """
#     _components[component_type] = instance
#     logger.debug(f"Registered component: {component_type.__name__}")


# def get_component(component_type: Type[T]) -> T:
#     """
#     Get a registered component by type.
    
#     Args:
#         component_type: Type of component to retrieve
        
#     Returns:
#         The component instance
        
#     Raises:
#         ConfigError: If component is not registered
#     """
#     if component_type not in _components:
#         raise ConfigError(
#             message=f"Component not registered: {component_type.__name__}",
#             user_message="System configuration error"
#         )
    
#     return cast(T, _components[component_type])


# async def shutdown_application() -> None:
#     """
#     Properly shut down all application components in reverse initialization order.
#     """
#     global _initialized
    
#     if not _initialized:
#         logger.info("Application not initialized, nothing to shut down")
#         return
    
#     try:
#         logger.info("Shutting down application components")
        
#         # Perform any necessary cleanup here
#         # (e.g., close connections, flush caches, etc.)
        
#         # Clear component registry
#         _components.clear()
#         _initialized = False
        
#         logger.info("Application shutdown complete")
        
#     except Exception as e:
#         logger.error(f"Error during application shutdown: {str(e)}")


# def is_initialized() -> bool:
#     """
#     Check if the application is initialized.
    
#     Returns:
#         True if initialized, False otherwise
#     """
#     return _initialized 