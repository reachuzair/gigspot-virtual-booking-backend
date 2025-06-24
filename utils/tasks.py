import threading
from django.db import close_old_connections

def run_async(func, *args, **kwargs):
    """
    Run a function in a background thread.
    
    Args:
        func: The function to run asynchronously
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        threading.Thread: The thread that's running the function
    """
    def _wrapper(*args, **kwargs):
        try:
            # Execute the function
            return func(*args, **kwargs)
        except Exception as e:
            # Log any exceptions that occur in the thread
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in async task {func.__name__}: {str(e)}", 
                        exc_info=True)
        finally:
            # Ensure database connections are closed
            close_old_connections()
    
    # Create and start the thread
    thread = threading.Thread(
        target=_wrapper, 
        args=args, 
        kwargs=kwargs,
        daemon=True,  # Daemon threads will be killed when the main program exits
        name=f"AsyncTask-{func.__name__}"  # Helpful for debugging
    )
    thread.start()
    return thread
