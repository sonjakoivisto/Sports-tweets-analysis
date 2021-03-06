#import required packages
import pandas as pd
import spacy 
import spacy_stanza
import os
import stanza
import matplotlib.pyplot as plt
from pyproj import CRS
import geopandas as gpd
from shapely.geometry import Point
import time
import glob

# Define functions

def create_pipeline(lang, package_name):
    """
    Creates a stanza pipeline for the language given as argument. 
    
    Parameters:
    
    lang| String: abbreviation for language which pipeline you want to create eg. "fi" or "en". 
    """
    #to avoid an error
    os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
    #make the pipeline for tokenizing and lemmatization
    nlp_pipeline = stanza.Pipeline(lang, processors='tokenize, lemma', package=package_name)
    nlp = spacy_stanza.StanzaLanguage(nlp_pipeline)
    print("Stanza pipeline created for language: " + lang)
    return nlp

def create_lemmas(df, nlp_lang):
    """
    Lemmatises text in dataframe column 'full_text'. Takes the name of the dataframe and 
    nlp pipeline for the correct language. Supposes that all tweets have the same language.
    Returns the same dataframe with two additional fields: lemmas (a list of lemmas) and 
    lemma_text (text containing only the lemmas)
    
    Parameters:
    
    df| String: Pandas dataframe to lemmatize
    nlp_lang| String: Name of Stanza Pipeline for the language corresponding to the dataframe
    """
    start_time = time.time()
    
    df["lemmas"] = None
    df["lemma_text"] = None

    for i in df.index:
    
        tweet_text = df.loc[i, "full_text"]
        
        #check for emojis and decode them
        #if(emojis.count(tweet_text) > 0):
            #tweet_text = emojis.decode(df.loc[i, "full_text"])
        try:
            #lemmatise the text
            doc = nlp_lang(tweet_text)

            lemmas = []
            lemma_text = ""
        
            #access the lemmas and add to the dataframe
            for token in doc:
                token.lemma_ = token.lemma_.replace("#", "")
                token.lemma_ = token.lemma_.replace("oitta", "oittaa")
                token.lemma_ = token.lemma_.replace("palohe", "palohein??")
                lemmas.append(token.lemma_)
                lemma_text += " " + token.lemma_
    
            df.at[i, "lemmas"] = lemmas 
            df.at[i, "lemma_text"] = lemma_text
        
            
        except IndexError:
            print("Encountered Index Error")
        
        #print the time it took to lemmatise x amount of tweets
        tweet_count = len(df)
        total_time = round((time.time() - start_time)/60, 3)
        
    #print("--- Lemmatising %s tweets took %s minutes ---" % (tweet_count, total_time))
    return df


def get_sports_tweets(df, keyword_list):
    """
    Searches for matches to sports-related keywords from a dataframe that has been lemmatised.

    Parameters:
    
    df | String: name of Pandas dataframe with lemmatized tweets 
    keyword_list | list of strings: list of sports-related words to search from the tweets
    """

    sports_df = pd.DataFrame()

    for i, row in df.iterrows():
        
        try:
            #check if keywords are found in lemmas
            count = [lemma for lemma in df["lemmas"][i] if(lemma in keyword_list)]
    
            #append the matched rows to sports dataframe
            if len(count) > 0:
                sports_df = sports_df.append(row)
        
        except TypeError:
            print("Encountered a TypeError")
            
    print(str(len(sports_df)) + " tweets found with sports related keywords")
    return sports_df


def geocode(sportstogeocode, hmanames):
    """
    Geocodes the tweets in sportstogeocode dataframe based on the gazetteer saved in hmanames dataframe.
    
    Parameters:
    
    sportstogeocode | String: name of Pandas dataframe with ungeotagged tweets
    hmanames | String: name of GeoPandas dataframe holding gazetteer information
    """
    #create a list of the placenames for comparison purposes
    placenames = [i.lower() for i in list(hmanames["name"])]
    
    #create a new geodataframe which will hold the geocoded tweets
    sportshma = gpd.GeoDataFrame()
    
    for i, row in sportstogeocode.iterrows():
        
        try:
            #search if any lemmas match the list of placenames
            placelist = [lemma.lower() for lemma in sportstogeocode.loc[i, "lemmas"] if(lemma.lower() in placenames)]
    
            #if there are any placenames, retrieve the point for that place and add it to the tweet information
            if len(placelist) > 0:
                x = hmanames.loc[hmanames["name"]== placelist[0], "geometry"].values[0].x
                y = hmanames.loc[hmanames["name"]== placelist[0], "geometry"].values[0].y
                geom = hmanames.loc[hmanames["name"]== placelist[0], "geometry"].values[0]
                row["geometry"] = geom
                row["lon"] = x
                row["lat"] = y
                sportshma = sportshma.append(row)
 
        except TypeError:
            print("Encountered a TypeError")
            
    print(str(len(sportshma)) + " tweets succesfully geocoded")
    return sportshma

def parse_points(sportsgeotagged):
    """
    Takes geotagged tweets and parses the coordinates into points. Returns a geodataframe with the tweets which are geotagged inside Helsinki Metropolitan area.
    
    Parameters:
    
    sportsgeotagged | String: name of Pandas dataframe with geotagged tweets
    """
    #parse shapely points from coordinates and convert to epsg 3067
    sportsgeotagged["geometry"] = None
    
    
    geom = []
    for x, y in zip(sportsgeotagged['lon'], sportsgeotagged['lat']):
        try:
            geom.append(Point(x, y))
    
        except (ValueError, KeyError):
            geom.append(None)
            print("Value Error or Key Error while parsing points")
        
    sportsgeotagged['geometry'] = geom
    gdf = gpd.GeoDataFrame(sportsgeotagged, geometry="geometry")
    gdf.crs = CRS.from_epsg(4326).to_wkt()
    gdf = gdf.to_crs(epsg=3067)
    
    #intersect with HMA polygon, save the tweets that are inside AOI
    hma = gpd.read_file(r"data/PKS_postinumeroalueet_2020.shp")
    hma = hma.to_crs(epsg=3067)
    
    hmageotagged = gpd.overlay(gdf, hma, how="intersection")
    hmageotagged.drop(["Posno", "Toimip", "Toimip_ru", "Nimi", "Nimi_Ru", "Kunta", "Kunta_nro"], axis=1, inplace=True)

    return hmageotagged


# Workflow

#Download stanza nlp models (skips if they are already downloaded)
stanza.download("en")
stanza.download("fi")
stanza.download("et")

#create pipelines 
nlp_en = create_pipeline("en", "ewt")
nlp_fi = create_pipeline("fi", "tdt")
nlp_et = create_pipeline("et", "edt")

#get info from gazetteer
hmanames = gpd.read_file(r"hmagazetteer.shp")

#create a geodataframe for final output
final_df = gpd.GeoDataFrame()

#process each chunk of tweets with the following workflow
batchno = 1

for name in glob.glob(r"chunk*"):
   
    print("Processing batch " + str(batchno) + "/ 77")
    df = pd.read_csv(open(name), encoding='utf-8', engine='c')

    #separate English, Finnish and Estonian dataframes
    df_fi = df[df["lang"]=="fi"]
    df_en = df[df["lang"]=="en"]
    df_et = df[df["lang"]=="et"]

    #create lemmas for English, Finnish and Estonian tweets
    df_fi = create_lemmas(df_fi, nlp_fi)
    df_en = create_lemmas(df_en, nlp_en)
    df_et = create_lemmas(df_et, nlp_et)


    #retrieve sports related tweets based on keyword lists
    sportslist_fi = ["k??vely", "k??vell??", "k??veleminen" "juoksu", "juosta", "juokseminen", "hiihto", "hiiht????", "hiiht??minen",
                 "lenkki", "lenkkeily", "lenkkeill??", "treenata", "treenaaminen", "urheilla", "meloa", "melonta", "soutaa", 
                 "soutaminen", "patikointi", "patikoida", "patikoiminen",  
                  "treeni", "urheilu", "liikunta", "py??r??", "py??r??ily", "py??r??ill??", "py??r??ileminen", "j????kiekko", "hockey",
                  "jalkapallo", "tennis", "tanssi", "tanssia", "tanssiminen", "hiki", "hikoilla", "sulkapallo",
                     "s??hly", "salibandy", "lentopallo",  "lentis", "luistella", "luisteleminen", "luistelu", "kuntosali",
                     "koris","futis", "koripallo", "uinti", "uida", "uiminen", "kajakki", "pujehtia", "purjehdus", "l??tk??", "jooga", 
                     "squash", "k??ssi", "pingis", "p??yt??tennis"]

    sports_fi = get_sports_tweets(df_fi, sportslist_fi)

    sportslist_en = ["running", "run", "walk", "walking", "jog" ,"jogging", "hike", "hiking", "trek", "trekking", 
                  "bicycle", "bike", "biking","cycling", "exercise", "exercising", "ski", "skiing", "skate", "skating", 
                  "workout", "training", "sport", "sporting", "canoe", "canoeing", "ice-hockey", "basketball",
                 "hockey", "football", "tennis", "dance", "dancing", "rowing", "sweat", "sweating", "badminton",
                 "floorball", "volley", "volleyball",  "beach volley", "yoga","swimming", "swim", "sail", "sailing", 
                     "kayak", "kayaking", "squash", "tabletennis"]


    sports_en = get_sports_tweets(df_en, sportslist_en) 


    sportslist_et = ["jooksmine", "jooksma", "jooks", "k??ndimine", "k??nd", "k??ndima", "jalutama", "jalutus", 
                 "jalutamine", "s??rkimine", "s??rkima", "s??rk", "s??rksjooks", "matk", "matkamine", "matkama",
                   "jalgratas", "jalgrattas??it", "rattas??it", "treening", "treenima", "v??imlema", "v??imlemine", 
                 "uisutamine", "uisutama", "suusatama", "suusatamine", "sportima", "sportimine", "trenn", "sport", 
                 "j??usaal", "v??imla", "spordihall", "spordisaal", "korvpall", "koss", "kanuu",  "kanuutama", 
                 "kanuutamine", "kanuus??it", "j????hoki", "hoki", "jalgpall", "jalka", "tennis", "tants", 
                 "tantsimine", "tantsima", "s??udmine", "s??udma", "aerutama", "aerutamine", "higi", "higistama", 
                 "higistamine", "sulgpall", "b??dminton", "saalihoki", "volle", "rannavolle", "v??rkpall", 
                 "rannav??rkpall", "joogatama", "jooga", "ujuma", "ujumine", "meres??st",  "kajakis??it", "purjetama", 
                 "purjetamine", "squash", "seinatennis", "lauatennis"]


    sports_et = get_sports_tweets(df_et, sportslist_et)


    #combine dataframes of sports tweets
    sports = sports_en.append(sports_fi)
    sports = sports.append(sports_et)

    #here figure out which sports tweets already have geotags
    sportstogeocode = sports[sports['geom'].isna()]
    sportsgeotagged = sports[~(sports['geom'].isna())]

    #geocode the tweets without geolocation 
    sportshma = geocode(sportstogeocode, hmanames)
    
    #parse points from geotagged tweets, this was done separately to speed up the process
    #sportsgeotagged = parse_points(sportsgeotagged) 

    #combine back to the geocoded tweets and save to csv
    sportshma_combined = sportshma.append(sportsgeotagged)
    
    #save the chunk to csv as a backup and to test post-processing in advance
    sportshma_combined.to_csv("sports" + str(batchno) + ".csv")
    final_df = final_df.append(sportshma_combined)
    
    batchno += 1
 
#save to shapefile, delete list of lemmas defore that. Shapefile doesn't like lists.
final_df = final_df.drop(["lemmas"], axis=1)        
final_df.to_file("finaloutput.shp")
