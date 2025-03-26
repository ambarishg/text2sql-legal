import qdrant_client as qc
import qdrant_client.http.models as qmodels
from qdrant_client.http.models import *
from sentence_transformers import SentenceTransformer, CrossEncoder

from sentence_transformers import CrossEncoder

class ResultProcessor:
    def __init__(self):
        # Initialize the cross-encoder model once to avoid repeated initialization
        self.cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

    def _get_results_to_return(self, results, user_input, cross_encoder_use=False):
        """Returns sorted results based on cross-encoder scores."""
        
        if not results:
            print("No results found")
            return [], [], [], []

        # Step 1: Extract payloads using list comprehensions
        results_to_return = [result.payload['content'] for result in results]
        metadata_source_page_to_return = [result.payload['sourcepage'] for result in results]
        metadata_source_filename_to_return = [result.payload['sourcefile'] for result in results]
        reranker_score_to_return = [
            result.payload['@search.reranker_score']
            for result in results if '@search.reranker_score' in result.payload
        ]

        # If cross-encoder is not used, return the results as is
        if not cross_encoder_use:
            return results_to_return,metadata_source_filename_to_return,metadata_source_page_to_return,reranker_score_to_return

        # Step 2: Perform batch prediction with the cross-encoder
        cross_scores = self.cross_encoder.predict([[user_input, hit] for hit in results_to_return])

        # Step 3: Combine lists into tuples for sorting
        combined_lists = list(zip(
            results_to_return,
            metadata_source_filename_to_return,
            metadata_source_page_to_return,
            cross_scores
        ))

        # Step 4: Sort combined lists based on cross-encoder scores (descending order)
        sorted_combined = sorted(combined_lists, key=lambda x: x[3], reverse=True)

        # Step 5: Unpack sorted tuples back into separate lists
        results_to_return_sorted, \
        metadata_source_filename_to_return_sorted, \
        metadata_source_page_to_return_sorted, \
        cross_score_list_sorted = zip(*sorted_combined)

        # Convert tuples back to lists
        results_to_return_sorted = list(results_to_return_sorted)
        metadata_source_filename_to_return_sorted = list(metadata_source_filename_to_return_sorted)
        metadata_source_page_to_return_sorted = list(metadata_source_page_to_return_sorted)
        cross_score_list_sorted = list(cross_score_list_sorted)

        print(f"Results to return Length: {len(results_to_return_sorted)}")

        return (
            results_to_return_sorted,
            metadata_source_filename_to_return_sorted,
            metadata_source_page_to_return_sorted,
            reranker_score_to_return
        )



class QdrantHelper:
    def __init__(self,
                 URL,
                 API_KEY,
                 MODEL_NAME,
                 COLLECTION_NAME,
                 METRIC=qmodels.Distance.COSINE,
                 DIMENSION = 384,
                 RESULTS_LIMIT = 5,
                 CROSS_ENCODER_USE = False
                 ):
        self.client = qc.QdrantClient(url=URL,api_key=API_KEY)
        self.metric = METRIC
        self.dimension = DIMENSION
        self.model_name = MODEL_NAME
        self.collection = COLLECTION_NAME
        self.results_limit = RESULTS_LIMIT
        self.results_processor = ResultProcessor()
        self.cross_encoder_use = CROSS_ENCODER_USE
    
    def create_index(self,
                          COLLECTION_NAME,
                          ):
        self.collection = COLLECTION_NAME
        self.client.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=qmodels.VectorParams(
                    size=self.dimension, 
                    distance=self.metric
                ),
            )
        
    def upload_documents(self,
                         id_list,
                         embeddings_all,
                         payload_list):
        
        embeddings_all_len = len(embeddings_all)

        CHUNK_SIZE = 100
        for i in range(0, embeddings_all_len, CHUNK_SIZE):
            if(i+CHUNK_SIZE > embeddings_all_len -1):
                new_chunk = embeddings_all_len -1
            else:
                new_chunk = i+CHUNK_SIZE -1
            print("Inserting chunk", i , "to", new_chunk)
            self.client.upsert(
                collection_name=self.collection,
                points=qmodels.Batch(
                    ids = id_list[i:new_chunk],
                    vectors=embeddings_all[i:new_chunk],
                    payloads=payload_list[i:new_chunk]
                ),
            )
    def get_embedding_query_vector(self, query):
        """Get the vector of the query

        Args:
            query (string): user input

        Returns:
            _type_: vector of the query
        """
        model = SentenceTransformer(self.model_name)
        query_vector = model.encode(query)
        return query_vector
    
    def get_search_results(self, user_input, 
                           CATEGORY=None, 
                           user_id=None):
        # Generate the query vector from the user input
        query_vector = self.get_embedding_query_vector(user_input)

        print(user_input)
        print("################################")
        
        print(f"category = {CATEGORY}")
        print(f"user_id = {user_id}")
        
        # Initialize query_filter based on CATEGORY and user_id
        must_conditions = []
        
        # Add category condition if provided
        if CATEGORY and CATEGORY != '':
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=models.MatchValue(value=CATEGORY),
                )
            )
        
        # Add user_id condition if provided
        if user_id is not None:
            must_conditions.append(
                FieldCondition(
                    key="user_id",  # Assuming "UserId" is the field name in your database
                    match=models.MatchValue(value=user_id),
                )
            )
        
        # Create query filter only if there are conditions to apply
        query_filter = qmodels.Filter(must=must_conditions) if must_conditions else None
        
        # Perform the search with the constructed query vector and filter
        search_result = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector.tolist(), 
            query_filter=query_filter,
            limit=self.results_limit
        )
        
        return self.__get_results_to_return(search_result,user_input)

    def __get_results_to_return(self, results,user_input):

        """This returns the results to return
        """
        # results_to_return = []
        # metadata_source_filename_to_return = []
        # metadata_source_page_to_return = []
        # reranker_score_to_return = []

        # if not results:
        #     print("No results found")
            
        # for result in results:             
        #     results_to_return.append(result.payload['content'])

        #     if '@search.reranker_score' in result.payload:
        #         reranker_score_to_return.append(result.payload['@search.reranker_score'])
            
        #     metadata_source_page_to_return.append(result.payload['sourcepage'])
        #     metadata_source_filename_to_return.append(result.payload['sourcefile'])
        
        #     #We use a cross-encoder, to re-rank the results list to improve the quality
        #     cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

        #     cross_score_list =[]

        #     for hit in results_to_return:
        #         cross_score = cross_encoder.predict([user_input,hit])
        #         cross_score_list.append(cross_score)

        #     # Combine all lists into a single list of tuples
        #     combined_lists = list(zip(results_to_return, \
        #     metadata_source_filename_to_return, \
        #     metadata_source_page_to_return, \
        #     cross_score_list))

        #     # Sort combined lists based on the float values in the last position (index 3)
        #     sorted_combined = sorted(combined_lists, key=lambda x: x[3], reverse=True)

        #     # Unpack the sorted combined list back into separate lists
        #     results_to_return_sorted, \
        #     metadata_source_filename_to_return_sorted, \
        #     metadata_source_page_to_return_sorted, \
        #     cross_score_list_sorted= zip(*sorted_combined)

        #     # Convert tuples back to lists
        #     results_to_return_sorted = list(results_to_return_sorted)
        #     metadata_source_filename_to_return_sorted = list(metadata_source_filename_to_return_sorted)
        #     metadata_source_page_to_return_sorted = list(metadata_source_page_to_return_sorted)
        #     cross_score_list_sorted = list(cross_score_list_sorted)

        # print(f"Results to return Length: {len(results_to_return_sorted)}")
 
        #  return results_to_return_sorted, \
        #     metadata_source_filename_to_return_sorted, \
        #     metadata_source_page_to_return_sorted, reranker_score_to_return

        return self.results_processor._get_results_to_return(results, 
                                                             user_input,
                                                             self.cross_encoder_use)
    