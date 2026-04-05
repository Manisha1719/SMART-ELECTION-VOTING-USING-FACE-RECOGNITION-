from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017/")["smart_voting"]

