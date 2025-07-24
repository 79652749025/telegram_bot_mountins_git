class PostManager:  
    def __init__(self):  
        self.posts = []  # В реальности - БД  
    
    def add_post(self, post_data):  
        self.posts.append(post_data)  
    
    def get_next_post(self):  
        # Циклический возврат постов  
        if not self.posts:  
            return None  
        return self.posts.pop(0)  