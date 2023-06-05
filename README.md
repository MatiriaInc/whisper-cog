# Transcription Cog Module

This repository contains a Cog project to perform transcription. It is based on a combination of models, including Whisper AI's
Large-V2 Whisper model and Whisper X for forced alignment.

For more information on how to use Cog, visit [Cog's Getting Started Guide](https://github.com/replicate/cog/blob/main/docs/getting-started.md).

## Table of Contents
- [Installation](#installation)
- [Building The Project](#building)
- [Deployment](#deployment)
- [Usage](#usage)
- [Interfacing With Replicate Clients](#replicate)
- [Transcription and Forced Alignment Model](#model)
- [Model Usage](#modelusage)
- [Modes of Operation](#operation)
- [Caveats and Recommendations](#caveats)

<a name="installation"></a>
## Installation
You can install Cog by running the following commands:

```bash
sudo curl -o /usr/local/bin/cog -L https://github.com/replicate/cog/releases/latest/download/cog_`uname -s`_`uname -m`
sudo chmod +x /usr/local/bin/cog
```

We need to download the large-v2 model for caching:

```bash
wget https://openaipublic.azureedge.net/main/whisper/models/81f7c96c852ee8fc832187b0132e569d6c3065a3252ed18e56effd0b6a73e524/large-v2.pt
```

Then initialize the lyric fix submodule:

```bash
git submodule update --init
```

<a name="building"></a>
## Building The Project
To build a GPU version of this project, you must have an NVIDIA GPU.

If you prefer to build with CPU, simply set the `gpu` flag to `False` in the `cog.yaml` file. You can access it [here](https://github.com/MatiriaInc/whisper-cog/blob/main/cog.yaml).

With Cog installed, you can build and run predictions using the following command:

```bash
cog predict -i audio=@<path-to-file> -i lyrics=@<path-to-file>
```

<a name="deployment"></a>
## Deployment
If you want to deploy the model to Replicate, follow these steps:

1. Login to Cog:

```bash
cog login
```

2. Push the model:

```bash
cog push r8.im/<your-username>/<your-model-name>
```

Your username and model name must match the values you set on Replicate.

For more information on deploying the model to Replicate, refer to the [Replicate Deployment Guide](https://replicate.com/docs/guides/push-a-model).

<a name="usage"></a>
## Usage
Once you've pushed your model to Replicate, it will be visible on the website, and you can use the web-based form to run predictions using your model.

You can bake the model’s code, the trained weights, and the Docker environment into a Docker image. This image serves predictions with an HTTP server and can be deployed anywhere that Docker runs to serve real-time predictions.

Build the image with:

```bash
cog build -t transcribe
```

You can run this image with cog predict:

```bash
cog predict transcribe -i audio=@audio.wav -i lyrics=@lyrics.txt
```

Or, run it with Docker directly:

```bash
docker run -d --rm -p 5000:5000 transcribe
```

You can send inputs directly with curl:

```bash
curl http://localhost:5000/predictions -X POST \
    -H 'Content-Type: application/json' \
    -d '{"input": {"audio": "http://my-hosted-file.wav"}}'
```

<a name="replicate"></a>
## Interfacing With Replicate Clients
You can also use the Replicate clients to interface with yourmodels if you pushed them directly to Replicate.

<a name="model"></a>
## Transcription and Forced Alignment Model
This model, based on OpenAI's Whisper Large V-2, transcribes audio files and performs forced alignment. It's particularly designed for lyric video generation but is flexible enough to be used for other transcription purposes.

<a name="modelusage"></a>
### Usage
This model serves as a vital part of the pipeline for the generation of lyric videos. For this application, artists' lyrics MUST be provided and the FIX parameter should be set. However, it's not strictly limited to lyric video generation. The model can be used for transcribing any audio file by turning off the FIX flag, making it a versatile component for various applications.

<a name="operation"></a>
### Modes of Operation
The model can operate in three different modes, each with its own benefits and potential issues:

1. **Unisolated Audio (use_vad = False)**: Send a non-isolated audio file (including vocals and instrumentation). Although this mode tends to provide the best transcriptions, it's prone to failure loops in which whisper returns repeated text and ignores the provided audio.

2. **Isolated Audio without VAD (use_vad = False)**: Send an isolated audio file without performing voice activity detection. This mode is reliable, but it may encounter timing and transcription errors.

3. **Isolated Audio with VAD (use_vad = True)**: Send an isolated audio file and perform voice activity detection. This mode offers accurate timestamp timings, but it can sometimes miss sections of text to transcribe due to aggressive VAD and is sensitive to noise at the beginning and end sections of a song.

A warning flag will be returned if any inconsistencies occurred during the inference, regardless of the mode of operation.

<a name="caveats"></a>
### Caveats and Recommendations
This model is non-deterministic, meaning the same inputs might yield different results on separate runs. Also, Whisper can hallucinate during long periods of silence, which may cause issues. Whisper has been found to be about 95% accurate on transcription of normal speech, however, singing is a harder task. Like other generative models, this model can create incorrect or even offensive transcriptions. For this reason, it's crucial to have a human vet the transcriptions before releasing them to the general public.
