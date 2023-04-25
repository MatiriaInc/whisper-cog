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
from whisperx.vad import load_vad_model
from LyricFix.lyricMatch import fix_lyrics
import srt as srt_parser

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
        self.vad_pipeline = load_vad_model("cuda", 0.5, 0.363, use_auth_token=self.hf_token)
        self.model = whisper.load_model("large-v2", "cuda" if torch.cuda.is_available() else "cpu", download_root='.')
        self.alignment_model, self.metadata = whisperx.load_align_model(language_code="en", device="cuda" if torch.cuda.is_available() else "cpu")
    def predict(
        self,
        audio: Path = Input(description="The audio for transcription."),
        lyrics: Path = Input(default=None, description="Text for lyrics of the song."),
        use_vad: bool = Input(default=False, description="Use VAD to run transcription."),
        condition_on_previous_text: bool = Input(default=False, description="Condition prediction on previous text."),
        extend_duration: float = Input(default=2.0, description="Amount to pad input segments by. If not using vad then recommended to use 2 seconds."),
        fix: bool = Input(default=True, description="Run lyric match.")
    ) -> ModelOutput:
        """Run a single prediction on the model"""

        inputs = {
            'condition_on_previous_text': condition_on_previous_text
        }

        if use_vad:

            if not str(audio).endswith(".wav"):
                print(">>VAD requires .wav format, converting to wav as a tempfile...")

                audio_basename = os.path.splitext(os.path.basename(str(audio)))[0]
                input_audio_path = os.path.join(os.path.dirname(str(audio)), audio_basename + ".wav")
                ffmpeg.input(str(audio), threads=0).output(input_audio_path, ac=1).run(cmd=["ffmpeg"])
                audio = input_audio_path

            result = transcribe_with_vad(self.model, str(audio), self.vad_pipeline, verbose=False, language="en", **inputs)
        else:
            result = self.model.transcribe(str(audio), condition_on_previous_text=condition_on_previous_text, language="en")

        cache_path = Path(tempfile.mkdtemp()) / "cache.srt"

        with open(cache_path, "w", encoding="utf-8") as srt:
            srt.write(write_srt(result["segments"]))



        if fix and lyrics is not None:
            transcription = fix_lyrics(cache_path, open(str(lyrics)))

            # run forced alignment
            transcription_list = []
            transcription_generator = srt_parser.parse(transcription)
            srt_content = list(transcription_generator)

            for lyric in srt_content:
                lyric.content = lyric.content.replace("\n", "\n ")
                transcription_list.append(
                    {"text": lyric.content, "start": lyric.start.total_seconds(), "end": lyric.end.total_seconds()})

            result_aligned = whisperx.align(transcription_list, self.alignment_model, self.metadata, str(audio), device="cuda" if torch.cuda.is_available() else "cpu", extend_duration=extend_duration)
            reinsertion_of_line_carriage(result_aligned, str(lyrics))

        else:
            result_aligned = whisperx.align(result["segments"], self.alignment_model, self.metadata, str(audio), device="cuda" if torch.cuda.is_available() else "cpu")

        srt_path = Path(tempfile.mkdtemp()) / "transcription.srt"
        aligned_word_srt_path = Path(tempfile.mkdtemp()) / "word_aligned.srt"
        aligned_srt_path = Path(tempfile.mkdtemp()) / "transcription_aligned.srt"


        open(srt_path, "w").write(write_srt(result["segments"]))
        open(aligned_srt_path, "w").write(write_srt(result_aligned["segments"]))
        open(aligned_word_srt_path, "w").write(write_srt(result_aligned["word_segments"]))


        return ModelOutput(detected_language=result["language"],transcription=result_aligned["word_segments"], srt_file=Path(srt_path), aligned_srt_file=Path(aligned_srt_path), aligned_word_srt_file=Path(aligned_word_srt_path))


def reinsertion_of_line_carriage(result_aligned, artist_lyrics):
    # we need the carriage returns to be in the word level data, but whisperx
    # removes them when aligning and doesn't add them back in.
    # We could either update whisperx to include the carriage returns
    # (in which case we have to post our changes)
    # or we could perhaps use the word level srt when we run lyric repair?
    # and add the carriage-returns back in then, maybe?
    # lyrics = open(artist_lyrics, "r", encoding="utf-8")
    # lyric_phrases = lyrics.readlines()

    lyric_phrases = []
    line_text = ""

    for segment in result_aligned['segments']:
        lines = segment['text'].splitlines()

        for line in lines:

            line_text += line if line_text == "" else (" " + line)

            if '\\n' in line.split()[-1]:
                lyric_phrases.append(line_text.replace('\\n', ''))
                line_text = ""


    new_aligned = []
    # Let's split words now.
    for wi, word in enumerate(result_aligned["word_segments"]):
        for split_entry in word["text"].split():
            new_entry = word.copy()
            new_entry["text"] = split_entry
            new_aligned.append(new_entry)

    result_aligned["word_segments"] = new_aligned

    word_index = 0
    for phrase in lyric_phrases:
        words = phrase.split()
        num_words_in_phrase = len(words)
        final_word = words[-1:][0]

        # sadly, we can't assume there is only one word per word_aligned entry
        num_words_processed = 0
        to_be_patched = None
        while num_words_processed < num_words_in_phrase and word_index < len(result_aligned["word_segments"]):
            srt_content = result_aligned["word_segments"][word_index]
            num_words_processed += len(srt_content["text"].split())
            to_be_patched = result_aligned["word_segments"][word_index]
            word_index += 1

        target_word = to_be_patched["text"]
        target_word.replace("\\n", "")
        if target_word == final_word:
            to_be_patched["text"] = target_word + '\\n'

def write_srt(transcript):
    result = ""
    srt_count = 1
    for i, segment in enumerate(transcript, start=1):
        if 'seg-start' in segment:
            for j in range(len(segment['seg-start'])):
                final_text = segment['seg-text'][j].strip().replace('-->', '->').replace('\n ', '\n')
                # final_text = final_text.replace('\\n', '')

                result += f"{srt_count}\n"
                result += f"{format_timestamp(segment['seg-start'][j] + segment['start'], always_include_hours=True, decimal_marker=',')} --> "
                result += f"{format_timestamp((segment['seg-end'][j] -  segment['seg-start'][j] ) + segment['seg-start'][j] + segment['start'], always_include_hours=True, decimal_marker=',')}\n"
                result += f"{final_text}\n"
                result += "\n"
                srt_count= srt_count + 1
        else:
            final_text = segment['text'].strip().replace('-->', '->').replace('\n ','\n')
            # final_text = final_text.replace('\\n', '')
            result += f"{srt_count}\n"
            result += f"{format_timestamp(segment['start'], always_include_hours=True, decimal_marker=',')} --> "
            result += f"{format_timestamp(segment['end'], always_include_hours=True, decimal_marker=',')}\n"
            result += f"{final_text}\n"
            result += "\n"
            srt_count = srt_count + 1

    return result
