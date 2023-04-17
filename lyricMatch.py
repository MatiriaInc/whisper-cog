import fuzzysearch
import pysrt
import num2words
import re



def closest_end_of_word(line, char):

    count = char
    print("THIS IS THE LINE:")
    print(line)
    for i in range(char - 1, len(line)):
        print("IN")
        print("CHARACTER: " + line[i])
        if line[i] == ' ' or line[i] == '\n':
            return i

        # if line[i + 1] == ' ' or line[i + 1] == '\n':
        #     return i + 1

def closest_start_of_word(line, char):
    count = char
    print("In the start: " + line)
    for i in reversed(range(char + 1)):
        prev_char = line[i-1]
        print(prev_char)
        if i == 0 or line[i - 1] == ' ' or line[i - 1] == '\n':
            return i


def char_to_word(line, char):
    word_count = 0
    for i in range(len(line)):
        if line[i] == ' ' or line[i] == '\n':
            word_count += 1
        if i == char:
            if line[i] == '\n' or line[i] == ' ':
                print("RETURNING HERE")
                print(line)
                print(line[i])
                return word_count
            # elif line[i] != '\n' and line[i] != 0 and line[i - 1] == '\n':
            #     return word_count + 1
            else:
                print("HAHAHA: " + line)
                print(line[i])

                return word_count

    return word_count + 1


def char_to_line(text, char):
    lines = text.splitlines()
    char_counts = []
    for i in range(len(lines)):
        if i == 0:
            char_counts.append(len(lines[i]))
        else:
            char_counts.append(len(lines[i]) + char_counts[i-1])

        if char <= char_counts[i] + 1:
            return i

def fix_lyric(current_line, next_prediction, extend, distance_rating, last_word, truth_words, try_count=0):
    if try_count == 6:
        return '', last_word, False
    current_line_words = current_line.split(' ')
    current_line_size = len(current_line_words)
    exact_words = truth_words[last_word: last_word + current_line_size + extend]

    sentence = ''
    print("----------------------------")
    for index in range(len(exact_words)):
        sentence = sentence + exact_words[index]

        if index != len(exact_words) - 1 and exact_words[index] != '' and exact_words[index][-1] != '\n':
            sentence = sentence + ' '

    print("PREDICTION(TARGET): " + current_line)
    print("SENTENCE:" + sentence)

    if len(current_line_words) > 2:
        last_words_on_prediction = current_line_words[-3] + ' ' + current_line_words[-2] + ' ' + current_line_words[
            -1] # + '\n'
    else:
        distance_rating = int(len(current_line) * 0.5)
        print("WAKA")
        print(distance_rating)
        last_words_on_prediction = ' '.join(current_line_words)

    print("MATCH: " + last_words_on_prediction)
    adaptive_rating = int(len(last_words_on_prediction) * 0.3)
    print("ADAPTIVE RATING: " + str(adaptive_rating))
    # distance_rating = adaptive_rating
    match = fuzzysearch.find_near_matches(last_words_on_prediction, sentence, max_l_dist=distance_rating)
    stop = []

    if next_prediction is not None:
        next_line = next_prediction
        next_line_words = next_line.split(' ')

        if len(next_line_words) > 2:
            next_distance = distance_rating
            next_line_first_words = next_line_words[0] + ' ' + next_line_words[1] + ' ' + next_line_words[2]
        else:
            next_line_first_words = next_line
            next_distance = int(len(next_line) * 0.5)

        stop = fuzzysearch.find_near_matches(next_line_first_words, sentence, max_l_dist=next_distance)
        print("STOP: " + next_line_first_words)

    final = ''
    ends = False

    if (len(stop) == 0) and len(match) > 0 and match[-1].matched != '':
        print("CASE 1: No stop but we matched the end.")
        end = closest_end_of_word(sentence, match[-1].end)
        print("THE END:")
        final = sentence[0: end]

        ends = end is None or sentence[end] == '\n'


        worded = char_to_word(sentence, end)
        print(match[-1])
        last_word = last_word + char_to_word(sentence, end)

    elif len(stop) != 0 and len(match) > 0 and match[-1].matched != '':
        print("CASE 2: Found stop and we matched the end.")

        if stop[-1].start > match[-1].end and stop[-1].matched != '':
            print("SUB 2a: Stop is beyond the end.")
            # TODO: RETURN TO END IF NOT WORKING OUT
            if match[-1].matched[-1] != '\n' and sentence[match[-1].end + 1] != ' ':
                print("SUB 2b: splitting words.")
                # print(stop)
                # best_match = 50
                # final_match = stop[-1]
                # for m in stop:
                #     print(m.start)
                #     if m.start > match[-1].end and m.dist < best_match:
                #         best_match = m.dist
                #         print(best_match)
                #         final_match = m
                #
                # print(final_match)
                # start = closest_start_of_word(sentence, final_match.start)
                # final = sentence[0: start]
                # last_word = last_word + char_to_word(sentence, start)
                end = closest_end_of_word(sentence, match[-1].end)
                final = sentence[0: end]
                ends = end is None or sentence[end] == '\n'
                last_word = last_word + char_to_word(sentence, end)
            else:
                print("SUB 2c: No splitting words.")
                end = closest_end_of_word(sentence, match[-1].end)
                final = sentence[0: end]
                ends = end is None or sentence[end] == '\n'
                last_word = last_word + char_to_word(sentence, end)
        else:
            print("SUB 2d: Stop is before the end, this means we might have some repetitions.")
            # TODO: Must fix for repetitions. Make it smarter. Use length ad heuristic.
            print(match)
            print(len(match))
            end_start = stop[-1].start
            latest = -1
            latest_index = 0
            for j in range(len(match)):
                if match[j].end >= latest and match[j].end < end_start:
                    latest = match[j].end
                    latest_index = j
            print('CHOSEN ONE: ')
            print(match[latest_index])
            end = closest_end_of_word(sentence, match[latest_index].end)
            final = sentence[0: end]
            ends = end is None or sentence[end] == '\n'
            last_word = last_word + char_to_word(sentence, end)
    elif len(match) == 0 and len(stop) != 0 and stop[-1].matched != '':
        print("CASE 3: Found stop but no match on the end.")

        start = closest_start_of_word(sentence, stop[-1].start)

        final = sentence[0: start]
        ends = start is None or sentence[start] == '\n'

        last_word = last_word + char_to_word(sentence, start)
    else:
        print("CASE 4: No stop and no match.")
        final, last_word, ends = fix_lyric(current_line, next_prediction, extend, distance_rating + 1, last_word, truth_words, try_count=try_count + 1)
        is_emoji = any(not c.isalnum() for c in current_line)

        if is_emoji:
            last_word = last_word
        else:
            if final == '':
                final = current_line
                # TODO: SHOULD WE UPDATE THE LINE SIZING. My guess is we could check percentage.
                last_word = last_word # + current_line_size

    return final, last_word, ends

def remspace(my_str):
    if len(my_str) < 2: # returns ' ' unchanged
        return my_str
    if my_str[-1] == '\n':
        if my_str[-2] == ' ':
            return my_str[:-2] + '\n'
    if my_str[-1] == ' ':
        return my_str[:-1]
    return my_str

def fix_lyrics(prediction_file, lyrics):
    prediction = pysrt.open(prediction_file)
    truth_lines = lyrics.readlines()
    truth_words = []
    for line in truth_lines:
        line = re.sub(r"(\d+)", lambda x: num2words.num2words(int(x.group(0))), line)
        truth_words.extend(remspace(line).split(' '))
    last_word = 0
    final_lyrics = ''
    while("" in truth_words):
        truth_words.remove("")

    while ("\n" in truth_words):
        truth_words.remove("\n")

    distance_rating = 3

    for i in range(len(prediction)):

        if last_word >=  len(truth_words) - 1:
            break

        final_lyrics += str(i + 1) + '\n'
        final_lyrics += str(prediction[i].start) + ' --> ' + str(prediction[i].end) + '\n'
        current_line = prediction[i].text
        current_line = re.sub(r"(\d+)", lambda x: num2words.num2words(int(x.group(0))), current_line)
        next_prediction = None
        if i < len(prediction) - 1:
            next_prediction = prediction[i+1].text
            next_prediction = re.sub(r"(\d+)", lambda x: num2words.num2words(int(x.group(0))), next_prediction)

        final, last_word, ends  = fix_lyric(current_line, next_prediction, 4, distance_rating, last_word, truth_words, try_count=0)

        if len(final) == 0:
            if(current_line[-1] != '\n'):
                final_lyrics += current_line + '\n'
        else:
            if final[-1] != '\n':
                if ends:
                    final = final + '\n'
                    final = final.replace('\n', '\\n\n')
                    final_lyrics += final
                else:
                    final = final.replace('\n', '\\n\n')
                    final_lyrics += final + '\n'
            else:
                final = final.replace('\n', '\\n\n')
                final_lyrics += final



        print("Final: " + final)

        final_lyrics += '\n'

    text_file = open("out.srt", "w")

    # write string to file
    text_file.write(final_lyrics)

    # close file
    text_file.close()

    print(truth_words)

    return final_lyrics

if __name__ == '__main__':
    prediction = "examples/eternity.srt"
    lyrics_file = open("examples/eternity.txt", "r")
    fix_lyrics(prediction, lyrics_file)

