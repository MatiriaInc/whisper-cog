import os
from cog import BaseModel, BasePredictor, Input, Path, File
import whisperx
import whisper
import torch
import tempfile
from whisper.utils import format_timestamp
from whisperx.asr import transcribe_with_vad
from typing import Optional, Any
import ffmpeg
from whisperx.vad import load_vad_model
from LyricFix.lyricMatch import fix_lyrics
import srt as srt_parser
from constants import *

class ModelOutput(BaseModel):
    detected_language: str
    transcription: Any
    srt_file: Path
    aligned_srt_file: Path
    aligned_word_srt_file: Path

class Predictor(BasePredictor):
    def setup(self):

        """
        This is called everytime there is a cold boot of the model
        We are loading the VAD model
        """

        # Even though it is looking for which device to use here, you must set cpu
        # or GPU in cog.yaml.
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.hf_token = HUGGINGFACE_TOKEN

        # Using default Onset and Offset as whisper x project.
        self.vad_pipeline = load_vad_model(self.device, VAD_ONSET, VAD_OFFSET, use_auth_token=self.hf_token)

        # Use download root . to make it look for the model in the local directory. That way we won't have to download
        # the model each time there is a cold boot.
        self.model = whisper.load_model(WHISPER_LARGE_V2, self.device, download_root='.')
        self.alignment_model, self.metadata = whisperx.load_align_model(language_code=LANGUAGE_ENGLISH, device=self.device)

    def predict(
        self,
        audio: Path = Input(description="The audio for transcription."),
        lyrics: Path = Input(default=None, description="Artist provided lyrics of the song."),
        use_vad: bool = Input(default=False, description="Use Voice Activity Detection (VAD) for transcription."),
        condition_on_previous_text: bool = Input(default=False, description="Condition prediction on previous text."),
        extend_duration: float = Input(default=2.0, description="Amount to pad input segments by. If not using VAD then recommended to use 2 seconds."),
        fix: bool = Input(default=True, description="Match transcription to artist provided lyrics.")
    ) -> ModelOutput:
        """Run a single prediction on the model"""

        inputs = {
            'condition_on_previous_text': condition_on_previous_text
        }

        if use_vad:

            # VAD can only deal with WAV files. If an MP3 is sent, then we will use FFMPEG to convert MP3 to WAV.
            if not str(audio).endswith(".wav"):
                print(">>VAD requires .wav format, converting to wav as a tempfile...")
                audio_basename = os.path.splitext(os.path.basename(str(audio)))[0]
                input_audio_path = os.path.join(os.path.dirname(str(audio)), audio_basename + ".wav")
                ffmpeg.input(str(audio), threads=0).output(input_audio_path, ac=1).run(cmd=["ffmpeg"])
                audio = input_audio_path

            result = transcribe_with_vad(self.model, str(audio), self.vad_pipeline, verbose=False, language=LANGUAGE_ENGLISH, **inputs)
        else:
            result = self.model.transcribe(str(audio), condition_on_previous_text=condition_on_previous_text, language=LANGUAGE_ENGLISH)

        # Write Raw SRT to cache
        cache_path = Path(tempfile.mkdtemp()) / OUTPUT_CACHE_SRT
        with open(cache_path, "w", encoding="utf-8") as srt:
            srt.write(get_srt_string(result[KEY_SEGMENTS]))

        # If there are artist provided lyrics and we are asked to match/fix the transcription.
        if fix and lyrics is not None:

            # Run lyric fix...
            transcription = fix_lyrics(cache_path, open(str(lyrics)))

            transcription_list = []
            transcription_generator = srt_parser.parse(transcription)
            srt_content = list(transcription_generator)

            # Prepare fixed transcription for forced alignment. Whisper X doesn't deal well with new line characters
            # without a space in the end. Add that space and put the transcription in dictionary structure that
            # it understands.
            for lyric in srt_content:
                lyric.content = lyric.content.replace("\n", "\n ")
                transcription_list.append(
                    {"text": lyric.content, "start": lyric.start.total_seconds(), "end": lyric.end.total_seconds()})

            # Force alignment to get back word level timestamps.
            result_aligned = whisperx.align(transcription_list, self.alignment_model, self.metadata, str(audio), device=self.device, extend_duration=extend_duration)

            # Recover new line characters.
            reinsertion_of_line_carriage(result_aligned)

        else:
            # If no lyric fix required, simply pass on whisper's raw transcription.
            result_aligned = whisperx.align(result[KEY_SEGMENTS], self.alignment_model, self.metadata, str(audio), device=self.device)

        # Create temporary files to serve as model's output.
        srt_path = Path(tempfile.mkdtemp()) / OUTPUT_RAW_SRT
        aligned_word_srt_path = Path(tempfile.mkdtemp()) / OUTPUT_ALIGNED_WORDS_SRT
        aligned_srt_path = Path(tempfile.mkdtemp()) / OUTPUT_ALIGNED_PHRASE_SRT

        # Write transcription results to output files.
        open(srt_path, "w").write(get_srt_string(result[KEY_SEGMENTS]))
        open(aligned_srt_path, "w").write(get_srt_string(result_aligned[KEY_SEGMENTS]))
        open(aligned_word_srt_path, "w").write(get_srt_string(result_aligned[KEY_WORD_SEGMENTS]))

        return ModelOutput(detected_language=result[KEY_LANGUAGE],transcription=result_aligned[KEY_WORD_SEGMENTS], srt_file=Path(srt_path), aligned_srt_file=Path(aligned_srt_path), aligned_word_srt_file=Path(aligned_word_srt_path))


def reinsertion_of_line_carriage(result_aligned):
    # We need the carriage returns to be in the word level data, but whisperx
    # removes them when aligning and doesn't add them back in. Add them back in here.
    # Luckily the carriage return is still there in the phrase level data.

    lyric_phrases = []
    line_text = ""

    # First we build a list of phrases, using the existing carriage returns. These represent
    # the way the artist and whisper have introduced new lines into the text.
    for segment in result_aligned[KEY_SEGMENTS]:
        lines = segment[KEY_TEXT].splitlines()

        for line in lines:

            # Append space only if the line is empty.
            line_text += line if line_text == "" else (" " + line)

            # If a new line character exists in the last word of a line, then we have found an artist introduced break.
            # Add the accumulated text as a "full line."
            if '\\n' in line.split()[-1]:
                lyric_phrases.append(line_text.replace('\\n', ''))
                line_text = ""


    new_aligned = []

    # Now we go through the words (which don't have carriage return). Note that the words and the lines are 1:1.
    # Unfortunately the aligner sometimes pairs more than one word into a word segment. This usually happens with
    # numbers, foreign characters, etc. So lets create a copy of the word segments, splitting "words" that contain more
    # than one word in them.
    for wi, word in enumerate(result_aligned[KEY_WORD_SEGMENTS]):
        for split_entry in word[KEY_TEXT].split():
            new_entry = word.copy()
            new_entry[KEY_TEXT] = split_entry
            new_aligned.append(new_entry)

    # Replace the old structure with the correct one that has been copied.
    result_aligned[KEY_WORD_SEGMENTS] = new_aligned

    # Go through every phrase. Find the last word of the phrase in the word structure. Add a carriage return to that
    # word.
    word_index = 0
    for phrase in lyric_phrases:
        words = phrase.split()
        num_words_in_phrase = len(words)

        final_word = words[-1:][0]

        # We can't assume there is only one word per word_aligned entry, just to be sure.
        num_words_processed = 0
        to_be_patched = None
        while num_words_processed < num_words_in_phrase and word_index < len(result_aligned[KEY_WORD_SEGMENTS]):
            srt_content = result_aligned[KEY_WORD_SEGMENTS][word_index]
            num_words_processed += len(srt_content[KEY_TEXT].split())
            to_be_patched = result_aligned[KEY_WORD_SEGMENTS][word_index]
            word_index += 1

        target_word = to_be_patched[KEY_TEXT]
        target_word.replace("\\n", "")
        if target_word == final_word:
            to_be_patched[KEY_TEXT] = target_word + '\\n'

def get_srt_string(transcript):
    """
    Get the SRT string that can be written to file from the dictionary structure returned from whisper's transcription.
    :param transcript: Whisper output of a transcription. Can be phrase level segments or word level segments.
    :return: A string with the contents of the final srt file generated from the whisper transcription.
    """

    # This will hold the full contents of the srt file. Let's build it.
    result = ""

    # SRT files start at 1 not 0.
    srt_count = 1

    # Go through every segment from whisper.
    for i, segment in enumerate(transcript, start=1):

        # If VAD was used, segments have sub-segments (fragments). We want to write each fragment as its own
        # segment so we don't have super long transcription blocks.
        if KEY_FRAGMENT_START in segment:

            # Iterate over every fragment (sub-segment)
            for j in range(len(segment[KEY_FRAGMENT_START])):

                # Remove any trailing spaces introduced by alignment.
                final_text = segment[KEY_FRAGMENT_TEXT][j].strip().replace('-->', '->').replace('\n ', '\n')

                result += f"{srt_count}\n"

                # Start time will be the Full segment start + the Fragment's start.
                result += f"{format_timestamp(segment[KEY_FRAGMENT_START][j] + segment[KEY_FULL_SEGMENT_START], always_include_hours=True, decimal_marker=',')} --> "

                # End time will be the beginning of the fragment + the fragment's duration.
                result += f"{format_timestamp((segment[KEY_FRAGMENT_END][j] -  segment[KEY_FRAGMENT_START][j] ) + segment[KEY_FRAGMENT_START][j] + segment[KEY_FULL_SEGMENT_START], always_include_hours=True, decimal_marker=',')}\n"
                result += f"{final_text}\n"
                result += "\n"
                srt_count= srt_count + 1
        else:

            # Otherwise just use the segment information and write in the format.
            # Remove any trailing spaces introduced by alignment.
            final_text = segment[KEY_TEXT].strip().replace('-->', '->').replace('\n ','\n')
            result += f"{srt_count}\n"
            result += f"{format_timestamp(segment[KEY_FULL_SEGMENT_START], always_include_hours=True, decimal_marker=',')} --> "
            result += f"{format_timestamp(segment[KEY_FULL_SEGMENT_END], always_include_hours=True, decimal_marker=',')}\n"
            result += f"{final_text}\n"
            result += "\n"
            srt_count = srt_count + 1

    return result
