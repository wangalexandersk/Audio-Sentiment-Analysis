import sys
import os
import json
import gcsfs
import requests
from google.cloud import speech
from google.cloud import storage
from google.cloud import language_v1
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for,jsonify 
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

app = Flask(__name__)

def upload_to_bucket(blob_name, path_to_file, bucket_name):
    """ Upload data to a bucket"""

    # Explicitly use service account credentials by specifying the private key
    # file.
    storage_client = storage.Client.from_service_account_json(
        'credentials.json')

    #print(buckets = list(storage_client.list_buckets())
    print ("Uploading...")
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(path_to_file)
    print ("Upload Complete")

    #returns a public url
    pub_url = urlparse(blob.public_url)
    gcs_url = "gs:/"+str(pub_url.path)
    print (gcs_url)
    return gcs_url

def transcribe_gcs(gcs_uri):

    client = speech.SpeechClient.from_service_account_json('credentials.json')

    audio_file_name = gcs_uri.split('/')[-1]
    if not audio_file_name:
        audio_file_name = 'out'
    audio_file_name = audio_file_name.replace('.flac', '')

    client = speech.SpeechClient.from_service_account_json('credentials.json')

    audio = speech.RecognitionAudio(uri=gcs_uri)
    # config = speech.RecognitionConfig(
    #     encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    #     sample_rate_hertz=8000,
    #     language_code="en-US",
    # )

    config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=44100,
    language_code="en-US",
    )
    operation = client.long_running_recognize(config=config, audio=audio)

    print("Waiting for response to complete...")
    response = operation.result(timeout=1000)

    lines = []
    for result in response.results:
        # The first alternative is the most likely one for this portion.
        lines.append(result.alternatives[0].transcript)
        #print(u'Transcript: {}'.format(lines[-1]))
        #print('Confidence: {}'.format(result.alternatives[0].confidence))

    if lines:
        fout_file = audio_file_name + '.txt'
        print('Write', fout_file)
        with open(fout_file, 'w') as fout:
            fout.write('\n'.join(lines))

    print ("Uploading Transcript...")
    transcript_gcs_url = upload_to_bucket(fout_file,fout_file,'audio_transcripts_raw')
    print ("Uploading Complete")
    return (transcript_gcs_url)

def analyze_sentiment(text_content):

    client = language_v1.LanguageServiceClient.from_service_account_json('credentials.json')
    type_ = language_v1.Document.Type.PLAIN_TEXT

    language = "en"
    document = {"content": text_content, "type_": type_, "language": language}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language_v1.EncodingType.UTF8

    response = client.analyze_sentiment(request = {'document': document, 'encoding_type': encoding_type})

    output = json.dumps({'Document sentiment score':response.document_sentiment.score,'Document sentiment magnitude':response.document_sentiment.magnitude}, sort_keys=False, indent=4)
    return (output)

def read_gcs_file(gcs_txt_path):

    gcs_file_system = gcsfs.GCSFileSystem(project="call-text-analysis", token='credentials.json')
    with gcs_file_system.open(gcs_txt_path) as f:
        text_content = f.read()
    print ("Read from Bucket Complete")
    return text_content

def main(file_name):
    audio_gcs_path = upload_to_bucket(file_name,file_name,'audio_records_conference_calls')
    transcript_gcs_path = transcribe_gcs(audio_gcs_path)
    text_content = read_gcs_file(transcript_gcs_path)
    sent_results = analyze_sentiment(text_content)
    return jsonify(Transcribed_text=text_content,Score=sent_results)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/', methods=['POST'])
def display_results():
    uploaded_file = request.files['file']
    print (uploaded_file.filename)
    if uploaded_file.filename != '':
        #uploaded_file.save(uploaded_file.filename)
        audio_gcs_path = upload_to_bucket(uploaded_file.filename,uploaded_file.filename,'audio_records_conference_calls')
        transcript_gcs_path = transcribe_gcs(audio_gcs_path)
        text_content = read_gcs_file(transcript_gcs_path)
        sent_results = analyze_sentiment(text_content)
        #return results
    return render_template('results.html', output=text_content,results=sent_results)

# Default port:
if __name__ == '__main__':
    app.run(host='localhost', port=5000)