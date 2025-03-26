from langchain_community.tools import DuckDuckGoSearchRun
class DuckDuckGoSearch:

    def __init__(self):
        pass

    def search(self, search_query):
        """Search the web for information on a given topic"""
        return DuckDuckGoSearchRun().run(search_query)