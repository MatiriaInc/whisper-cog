# Prediction interface for Cog ⚙️
# https://github.com/replicate/cog/blob/main/docs/python.md

import os
from cog import BaseModel, BasePredictor, Input, Path, File
import whisperx
import whisper
import torch
import tempfile
from io import BytesIO
from whisper.utils import format_timestamp
from pyannote.audio import Inference
from whisperx.asr import transcribe_with_vad
from typing import Optional, Any
import ffmpeg
from whisper.audio import SAMPLE_RATE

class ModelOutput(BaseModel):
    detected_language: str
    transcription: Any
    srt_file: Path
    aligned_srt_file: Path
    aligned_word_srt_file: Path

class Predictor(BasePredictor):
    def setup(self):
        """Load the model into memory to make running multiple predictions efficient"""
        self.hf_token = "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"
        self.vad_pipeline = Inference(
                "pyannote/segmentation",
                pre_aggregation_hook=lambda segmentation: segmentation,
                use_auth_token=self.hf_token,
                device="cuda" if torch.cuda.is_available() else "cpu"
            )
        self.model = whisper.load_model("large-v2", "cuda" if torch.cuda.is_available() else "cpu")
        self.alignment_model, self.metadata = whisperx.load_align_model(language_code="en", device="cuda" if torch.cuda.is_available() else "cpu")
    def predict(
        self,
        audio: Path = Input(description="The audio for transcription"),
        use_vad: bool = Input(default=False, description="Use VAD to run transcription.")

    ) -> ModelOutput:
        """Run a single prediction on the model"""
        inputs = {
            'condition_on_previous_text': False
        }



        if use_vad:

            if not str(audio).endswith(".wav"):
                print(">>VAD requires .wav format, converting to wav as a tempfile...")

                audio_basename = os.path.splitext(os.path.basename(str(audio)))[0]
                input_audio_path = os.path.join(os.path.dirname(str(audio)), audio_basename + ".wav")
                ffmpeg.input(str(audio), threads=0).output(input_audio_path, ac=1, ar=SAMPLE_RATE).run(cmd=["ffmpeg"])
                audio = input_audio_path

            result = transcribe_with_vad(self.model, str(audio), self.vad_pipeline, verbose=True, language="en", **inputs)
        else:
            result = self.model.transcribe(str(audio))

        result_aligned = whisperx.align(result["segments"], self.alignment_model, self.metadata, str(audio), device="cuda" if torch.cuda.is_availabl\
e() else "cpu")

        srt_path = Path(tempfile.mkdtemp()) / "transcription.srt"
        aligned_word_srt_path = Path(tempfile.mkdtemp()) / "word_aligned.srt"
        aligned_srt_path = Path(tempfile.mkdtemp()) / "transcription_aligned.srt"


        open(srt_path, "w").write(write_srt(result["segments"]))
        open(aligned_srt_path, "w").write(write_srt(result_aligned["segments"]))
        open(aligned_word_srt_path, "w").write(write_srt(result_aligned["word_segments"]))


        return ModelOutput(detected_language=result["language"],transcription=result_aligned["word_segments"], srt_file=Path(srt_path), aligned_srt_\
file=Path(aligned_srt_path), aligned_word_srt_file=Path(aligned_word_srt_path))



def write_srt(transcript):
    result = ""
    for i, segment in enumerate(transcript, start=1):
        result += f"{i}\n"
        result += f"{format_timestamp(segment['start'], always_include_hours=True, decimal_marker=',')} --> "
        result += f"{format_timestamp(segment['end'], always_include_hours=True, decimal_marker=',')}\n"
        result += f"{segment['text'].strip().replace('-->', '->')}\n"
        result += "\n"

    return result
