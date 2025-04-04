import logging.config
from pathlib import Path
from PIL import Image

from azure_blob.azure_blob_helper import AzureBlobHelper
from azure_blob.read_pdf import PDFHelper
from config import *
from azure_ai_search.azure_ai_vector_search import CustomAzureSearch
from azureopenaimanager.azureopenai_helper import AzureOpenAIManager
import base64
from azurequeues import azure_queue_helper
import logging
from cosmos.cosmosdbmanager import CosmosDBManager
import pandas as pd
from fastapi import UploadFile, File, Form
from sqlmanager.azuresqlmanager import AzureSQLManager

from pydantic import BaseModel
from typing import Dict, Any, List

from api.chat import ChatResponse
from api.getFiles import FilesResponse
from api.conversation import ConversationHeaders, ConversationHistory
from file_load_status_helper.file_load_status_helper import CosmosDBLoadStatusHelper
from file_load_status_helper.interface_load_status_helper import ILoadStatusHelper
import io
import json 
import uuid


class DataFrameResponse(BaseModel):
    dataframe: List[Dict[str, Any]]
    sql_query: str

async def summarize(filename:str,
                      category: str,
                      user_id: str):
   
    logging.basicConfig(level=logging.INFO)

    logging.info(f"User id is {user_id}")
    logging.info(f"Category is {category}")
    logging.info(f"File name is {filename}")  

    
    queue_service = azure_queue_helper.AzureQueueService(AZURE_QUEUE_STORAGE_ACCOUNT,
                                                        AZURE_QUEUE_STORAGE_KEY,
                                                        AZURE_QUEUE_NAME)
    
    cosmos_db_helper = CosmosDBManager(COSMOSDB_ENDPOINT,
                                    COSMOSDB_KEY,
                                    COSMOSDB_DATABASE_NAME,
                                    COSMOSDB_CONTAINER_NAME)
    
    
    message = {"filename": filename,
    "category": category, "user_id": user_id,"purpose":"SUMMARIZE"}

    # Convert the dictionary to a JSON string
    import json
    message_str = json.dumps(message)
    queue_service.send_message(message_str)

    logging.info(f"File {filename} sent to queue for summarizing.")

    file_load_status_helper = CosmosDBLoadStatusHelper()
    
    item = {"filename": filename,
    "category": category, 
    "user_id": user_id, 
    "summarize_status":"SENT TO SUMMARIZE"}

    file_load_status_helper.set_file_summarize_status(item)


async def upload_docs(file_data: UploadFile = File(...),
                      category: str = Form(...),
                      user_id: str = Form(...)):

    """
    Uploads the document to Azure Blob Storage and Azure Search
    :param SAVED_FOLDER: The folder where the document is saved
    :param FILE_NAME: The name of the file to be uploaded
    :return: None

    
    """
   
    logging.basicConfig(level=logging.INFO)

    logging.info(f"User id is {user_id}")
    logging.info(f"Category is {category}")
    logging.info(f"File name is {file_data.filename}")  

    azure_blob_helper_datasource = AzureBlobHelper(AZ_ST_ACC_NAME,
                                                AZ_ST_ACC_KEY,
                                                AZ_ST_DATASOURCE_CONTAINER_NAME)
    queue_service = azure_queue_helper.AzureQueueService(AZURE_QUEUE_STORAGE_ACCOUNT,
                                                        AZURE_QUEUE_STORAGE_KEY,
                                                        AZURE_QUEUE_NAME)
    
    cosmos_db_helper = CosmosDBManager(COSMOSDB_ENDPOINT,
                                    COSMOSDB_KEY,
                                    COSMOSDB_DATABASE_NAME,
                                    COSMOSDB_CONTAINER_NAME)
    
    content = await file_data.read()
    file_name = file_data.filename
    azure_blob_helper_datasource.upload_blob(content, file_name)
    message = {"full_path": 
    f"https://{AZ_ST_ACC_NAME}.blob.core.windows.net/{AZ_ST_DATASOURCE_CONTAINER_NAME}/{file_name}",
    "category": category, "user_id": user_id,"purpose":"INDEX"}

    # Convert the dictionary to a JSON string
    import json
    message_str = json.dumps(message)
    queue_service.send_message(message_str)

    logging.info(f"File {file_name} sent to queue for indexing.")

    file_load_status_helper = CosmosDBLoadStatusHelper()
    
    item = {"filename": file_name,
    "category": category, 
    "user_id": user_id, 
    "status":"UPLOADED"}

    file_load_status_helper.set_file_load_status(item)



def get_reply(user_input, content, token = None, conversation_id = None):

    
    cosmosdb_helper = CosmosDBManager(COSMOSDB_ENDPOINT,    
                                    COSMOSDB_KEY, 
                                    COSMOSDB_DATABASE_NAME, 
                                    COSMOSDB_CONTAINER_NAME_CONVERSATIONS)
    
    azure_open_ai_manager = AzureOpenAIManager(
                    endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_KEY,
                    deployment_id=AZURE_OPENAI_DEPLOYMENT_ID,
                    api_version="2023-05-15",
                    cosmosdb_helper = cosmosdb_helper,
                    token = token
                )             
    
    conversation=[{"role": "system", "content": "If the answer is not found within the context, please mention \
        that the answer is not found \
        Do not answer anything which is not in the context"}]
    reply,conversation_id = azure_open_ai_manager.generate_reply_from_context(user_input, 
                        content,conversation, conversation_id)
    return reply,conversation_id

def search_docs(query, token = None, conversation_id = None):
    """
    Searches for documents in Azure Search
    :param query: The query to search for
    :return: The search results
    
    """

    search = CustomAzureSearch(AZURE_SEARCH_SERVICE_ENDPOINT,
                            AZURE_SEARCH_ADMIN_KEY,
                            AZURE_SEARCH_INDEX_NAME,
                            NUMBER_OF_RESULTS_TO_RETURN,
                            NUMBER_OF_NEAR_NEIGHBORS,
                            MODEL_NAME,
                            EMBEDDING_FIELD_NAME,
                            AZURE_SEARCH_SEMANTIC_CONFIG_NAME)
    
    azure_blob_helper = AzureBlobHelper(AZ_ST_ACC_NAME,
                                    AZ_ST_ACC_KEY,
                                    AZ_ST_CONTAINER_NAME)
    results, \
                metadata_source_filename_to_return, \
                metadata_source_page_to_return, \
                    reranker_score =  search.get_results_semantic_search(query)
    
    context = "\n".join(results)
    reply,conversation_id = get_reply(query, context,token=token, conversation_id=conversation_id)

    URLs = []
    
    reranker_confidence = get_reranker_confidence(reranker_score)

    for page in metadata_source_page_to_return:
       URLs.append(azure_blob_helper.generate_sas_url(page))

    return ChatResponse(reply=reply[0], 
    metadata_source_page_to_return=metadata_source_page_to_return,
    URLs=URLs, reranker_confidence=reranker_confidence,
    conversation_id=conversation_id)

def get_reranker_confidence(reranker_score):
    """
    Get the confidence level of the reranker
    :param reranker_score: The score from the reranker
    :return: The confidence level
    
    """
    if reranker_score[0] < 2.6:
        reranker_confidence = "Low"
    elif reranker_score[0] < 3:
        reranker_confidence = "Medium"
    else:
        reranker_confidence = "High"
    return reranker_confidence

# Open the image file and encode it as a base64 string
def encode_image(data):
    return base64.b64encode(data).decode("utf-8")

async def get_image_analysis(image_data: UploadFile = File(...)):
    """
    Get image analysis from Azure Open AI
    :param image_data: The image data
    :return: The image analysis response
    
    """
    print("Inside get_image_analysis")
    azure_open_ai_manager_4o = AzureOpenAIManager(
                    endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_KEY,
                    deployment_id=AZURE_OPENAI_DEPLOYMENT_GPT_4O_ID,
                    api_version="2023-05-15"
                )
    from PIL import Image
    prompt = "Provide all the form values in the form of a JSON object."
    
    contents = await image_data.read()
    image_base64 = encode_image(contents)
    
    response = azure_open_ai_manager_4o.get_image_analysis(prompt,image_base64)

    print(f"The response is {response}")

    response = response.replace("```json", "").replace("```", "")

    response = json.loads(response)
    return response

async def get_simple_image_analysis(image_data: UploadFile = File(...)):
    """
    Get image analysis from Azure Open AI
    :param image_data: The image data
    :return: The image analysis response
    
    """
    print("Inside get_simple_image_analysis")
    azure_open_ai_manager_4o = AzureOpenAIManager(
                    endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_KEY,
                    deployment_id=AZURE_OPENAI_DEPLOYMENT_GPT_4O_ID,
                    api_version="2023-05-15"
                )
    from PIL import Image
    prompt = """
    
    Please mention the following items in pointwise fashion

     1.Please mention if there is any pollen associated with 
       the bees in the picture.
     2. How many bees are present
     3. How many are drone bees

    """

    # prompt = "Please describe the image in detail."
    
    contents = await image_data.read()
    image_base64 = encode_image(contents)
    
    response = azure_open_ai_manager_4o.get_image_analysis(prompt,image_base64)

    print(f"The response is {response}")
   
    return response


def get_indexed_files(user_id):
    """
    Get the uploaded files to index
    :return: The uploaded files
    
    """

    cosmos_db_manager = CosmosDBManager(COSMOSDB_ENDPOINT, 
                                    COSMOSDB_KEY, 
                                    COSMOSDB_DATABASE_NAME, COSMOSDB_CONTAINER_NAME)



    print(f"User id is {user_id}")
    query = f'SELECT * FROM c WHERE c.user_id = "{user_id}" ORDER BY c._ts DESC'

    print(f"Query is {query}")


    uploaded_files = cosmos_db_manager.read_items(query)

    li = []
    category_list = []
    status_list = []
    summarize_status_list = []
    summarize_URL_list = []

    for row in uploaded_files:
        logging.info(f"Row is {row}")
        li.append(row["filename"])
        category_list.append(row["category"])
        status_list.append(row["status"])
        if "summarize_status" in row:
            summarize_status_list.append(row["summarize_status"])
        else:
            summarize_status_list.append("")
        if "summarize_url" in row:
            summarize_URL_list.append(row["summarize_url"])
        else:
            summarize_URL_list.append("")
    
    return FilesResponse(file_list=li, 
                         category_list=category_list,
                         status_list = status_list,
                         summarize_status_list = summarize_status_list,
                         summarize_URL_list = summarize_URL_list)


def _get_SQL_query(user_input):
    
    return get_SQL_query(user_input, server, username, password, database)

def get_SQL_query(user_input,
                  server,
                  user_name,
                  password,
                  database):
  
  
    
  azure_open_ai_manager = AzureOpenAIManager(
                    endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_KEY,
                    deployment_id=AZURE_OPENAI_DEPLOYMENT_ID,
                    api_version="2023-05-15"
                )
  
  sql_query = None
  dict_df = None
    
  msg,_,_,_ = azure_open_ai_manager.generate_answer_document(user_input)

  if "```sql" not in msg:
        sql_query = None
  else:
        query = msg.split("```sql")[1].split("```")[0].strip().replace("\n", " ")
        sql_query = query

  if sql_query:
      # Create an instance of the AzureSQLManager

        print(sql_query)
        sql_helper = AzureSQLManager(server, \
                                     database, \
                                     user_name, \
                                     password)
        # Execute the query
        sql_helper.connect()
        results = sql_helper.execute_query_return(sql_query)
        df = pd.DataFrame.from_records(results)
        df.columns = ['col' + str(col) for col in df.columns]
        dict_df = df.to_dict('records')
  else:
        dict_df = None

  return DataFrameResponse(dataframe=dict_df, 
                           sql_query=sql_query)
  
def get_SQL_VARS():
    return server, database, username, password

def get_chat_history(conversation_id):
    cosmosdb_helper = CosmosDBManager(COSMOSDB_ENDPOINT,    
                                    COSMOSDB_KEY, 
                                    COSMOSDB_DATABASE_NAME, 
                                    COSMOSDB_CONTAINER_NAME_CONVERSATIONS)
    query = f'SELECT * FROM c WHERE c.conversation_id = "{conversation_id}"'
    items = cosmosdb_helper.read_items(query)
    
    return items

def get_recent_conversations():
    cosmosdb_helper = CosmosDBManager(COSMOSDB_ENDPOINT,    
                                    COSMOSDB_KEY, 
                                    COSMOSDB_DATABASE_NAME, 
                                    COSMOSDB_CONTAINER_NAME_CONVERSATIONS_HEADER)
    query = "SELECT * FROM c ORDER BY c._ts DESC"
    items = cosmosdb_helper.read_items(query)
    conversation_header_list = []
    for item in items:
        d= {}
        d["conversation_id"] = item["conversation_id"]
        d["short_name"] = item["short_name"]
        conversation_header_list.append(d)
    return ConversationHeaders(conversationsHeaders=
                               conversation_header_list)

def get_categories_user(user_id):
    cosmosdb_helper = CosmosDBManager(COSMOSDB_ENDPOINT,    
                                    COSMOSDB_KEY, 
                                    COSMOSDB_DATABASE_NAME, 
                                    COSMOSDB_CONTAINER_NAME_CONVERSATIONS_CATEGORY)
    query = f'SELECT * FROM c WHERE c.user_id = "{user_id}"'
    items = cosmosdb_helper.read_items(query)
    categories = set()
    for item in items:
        categories.add(item["category"])
    return list(categories)


