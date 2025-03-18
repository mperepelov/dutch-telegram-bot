import logging
import os
import json
import subprocess
import requests
import asyncio
from datetime import datetime
from gtts import gTTS
from moviepy.editor import *
from pysrt import SubRipFile, SubRipItem
import textwrap
from PIL import Image, ImageDraw, ImageFont
import time
import io

logger = logging.getLogger(__name__)

# Disable ImageMagick completely
import moviepy.config as conf
conf.change_settings({"IMAGEMAGICK_BINARY": None})

class DalleStoryGenerator:
    def __init__(self, llm_handler):
        self.llm_handler = llm_handler
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        # Create a temp directory within the project structure
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.temp_dir = os.path.join(self.base_dir, "story_temp")
        
        # Create the directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            
        # Handle ffmpeg path - check for ffmpeg in common locations
        self.ffmpeg_path = self._find_ffmpeg()
            
        logger.info(f"Initialized DalleStoryGenerator with temp directory: {self.temp_dir}")
        if self.ffmpeg_path:
            logger.info(f"Using ffmpeg from: {self.ffmpeg_path}")
        else:
            logger.warning("ffmpeg not found in PATH. Videos will be created without subtitles.")
            
    def _find_ffmpeg(self):
        """Find ffmpeg executable in PATH or common locations"""
        # Check if ffmpeg is in PATH
        try:
            # Simple check by running ffmpeg -version
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=False)
            return "ffmpeg"  # If no exception, ffmpeg is in PATH
        except FileNotFoundError:
            pass
            
        # Common locations to check for ffmpeg
        common_locations = [
            os.path.join(self.base_dir, "ffmpeg", "bin", "ffmpeg.exe"),  # Project directory
            os.path.join(self.base_dir, "ffmpeg.exe"),
            "C:\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe"
        ]
        
        for location in common_locations:
            if os.path.exists(location):
                return location
                
        return None
            
    def _create_story_prompt(self, user_prompt, level="beginner"):
        """Create a prompt for generating a story with scene descriptions"""
        levels = {
            "beginner": "Use very simple vocabulary and basic sentences. Focus on present tense.",
            "intermediate": "Use everyday vocabulary and some compound sentences. Include present and past tenses.",
            "advanced": "Use varied vocabulary and complex sentences. Include various tenses and some idiomatic expressions."
        }
        
        level_instruction = levels.get(level.lower(), levels["beginner"])
        
        prompt = f"""Generate a short story in Dutch based on this prompt: "{user_prompt}"

Story requirements:
- Language level: {level_instruction}
- Length: 4-6 scenes/paragraphs
- Include a title
- Make it engaging and descriptive
- Story should have a beginning, middle, and end

For each scene, provide:
1. A detailed visual description for image generation (be specific about what should be in the image)
2. The Dutch paragraph text
3. The English translation

Format:
Return a JSON object structured as follows:
{{
  "title_nl": "Dutch title",
  "title_en": "English translation of title",
  "scenes": [
    {{
      "image_prompt": "Detailed visual description for DALL-E image generation (in English)",
      "text_nl": "Dutch text for this scene",
      "text_en": "English translation of the text"
    }},
    ...more scenes...
  ]
}}

The JSON should be valid and parseable. Include no other text or explanation."""
        
        return prompt
        
    async def generate_story(self, user_prompt, level="beginner", model_name="gpt-4o"):
        """Generate a story in Dutch with English translation and scene descriptions"""
        try:
            logger.info(f"Generating story with prompt: {user_prompt}")
            
            # Get response from LLM
            story_prompt = self._create_story_prompt(user_prompt, level)
            response = await self.llm_handler.send_message(
                prompt=story_prompt,
                model_name=model_name,
                store_history=False,
                temperature=0.8,
                max_tokens=1500
            )
            
            # Process the response as JSON
            # Find JSON in response (in case model adds additional text)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("Could not find valid JSON in response")
                
            json_content = response[json_start:json_end]
            story_data = json.loads(json_content)
            
            # Validate story data
            required_fields = ['title_nl', 'title_en', 'scenes']
            for field in required_fields:
                if field not in story_data:
                    raise ValueError(f"Missing required field in story data: {field}")
                    
            if not story_data['scenes'] or len(story_data['scenes']) < 1:
                raise ValueError("Story must have at least one scene")
                
            for i, scene in enumerate(story_data['scenes']):
                if 'image_prompt' not in scene or 'text_nl' not in scene or 'text_en' not in scene:
                    raise ValueError(f"Scene {i+1} is missing required fields")
            
            logger.info(f"Successfully generated story with {len(story_data['scenes'])} scenes")
            return story_data
            
        except Exception as e:
            logger.error(f"Error generating story: {e}")
            raise
    
    async def generate_image(self, prompt):
        """Generate an image using DALL-E API"""
        try:
            if not self.openai_api_key:
                raise ValueError("OpenAI API key is not set")
                
            logger.info(f"Generating DALL-E image for prompt: {prompt[:50]}...")
            
            # Enhance the prompt for better storytelling imagery
            enhanced_prompt = f"A children's storybook illustration in a warm, friendly style showing: {prompt}. Vibrant colors, clear composition, no text or watermarks."
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.openai_api_key}"
            }
            
            data = {
                "model": "dall-e-3",
                "prompt": enhanced_prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard"
            }
            
            try:
                response = requests.post(
                    "https://api.openai.com/v1/images/generations",
                    headers=headers,
                    json=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    image_url = result["data"][0]["url"]
                    
                    # Download the image
                    image_response = requests.get(image_url)
                    
                    if image_response.status_code == 200:
                        # Convert to PIL Image
                        image = Image.open(io.BytesIO(image_response.content))
                        return image
                    else:
                        logger.error(f"Failed to download image: {image_response.status_code}, {image_response.text}")
                        return None
                else:
                    logger.error(f"DALL-E API error: {response.status_code}, {response.text}")
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error when calling DALL-E API: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating image: {e}")
            return None
    
    def _add_text_to_image(self, image, text_nl, text_en, title=None):
        """Add dual-language text overlay to an image"""
        try:
            # Create a copy of the image
            img_with_text = image.copy()
            draw = ImageDraw.Draw(img_with_text)
            
            # Try to get a font
            try:
                text_font = ImageFont.truetype("arial.ttf", 36)
                text_font_en = ImageFont.truetype("arial.ttf", 30)  # Slightly smaller for English
                title_font = ImageFont.truetype("arial.ttf", 48)
            except:
                text_font = ImageFont.load_default()
                text_font_en = ImageFont.load_default()
                title_font = ImageFont.load_default()
            
            # Add title if provided
            if title:
                # Create semi-transparent background for title at top
                title_height = 70
                overlay = Image.new('RGBA', (image.width, title_height), (0, 0, 0, 180))
                img_with_text.paste(Image.new('RGB', (image.width, title_height), (0, 0, 0)), 
                              (0, 0), 
                              overlay)
                
                # Add title text
                title_position = (20, 10)
                draw.text(title_position, title, font=title_font, fill=(255, 255, 255))
            
            # Create semi-transparent background for text at bottom
            # Make it taller to accommodate both languages
            text_box_height = 200
            text_box_y = image.height - text_box_height
            
            overlay = Image.new('RGBA', (image.width, text_box_height), (0, 0, 0, 180))
            img_with_text.paste(Image.new('RGB', (image.width, text_box_height), (0, 0, 0)), 
                          (0, text_box_y), 
                          overlay)
            
            # Wrap and add Dutch text
            wrapped_text_nl = textwrap.fill(text_nl, width=60)
            text_y = text_box_y + 20
            
            for line in wrapped_text_nl.split('\n'):
                text_position = (20, text_y)
                draw.text(text_position, line, font=text_font, fill=(255, 255, 255))  # White for Dutch
                text_y += 40
            
            # Add a small gap between languages
            text_y += 10
            
            # Wrap and add English text
            wrapped_text_en = textwrap.fill(text_en, width=70)  # Slightly wider for English
            
            for line in wrapped_text_en.split('\n'):
                text_position = (20, text_y)
                draw.text(text_position, line, font=text_font_en, fill=(173, 216, 230))  # Light blue for English
                text_y += 35  # Slightly less space for English text
                
            return img_with_text
            
        except Exception as e:
            logger.error(f"Error adding text to image: {e}")
            return image  # Return original image if there's an error
            
    def _text_to_speech(self, text, lang, output_file):
        """Convert text to speech using gTTS"""
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(output_file)
            return True
        except Exception as e:
            logger.error(f"Error in text-to-speech: {e}")
            return False
            
    def _create_subtitles(self, scenes, output_file, durations, is_dutch=True):
        """Create subtitle file (SRT format) from scenes"""
        try:
            subs = SubRipFile()
            current_time = 0
            
            # Add title scene
            title_duration = 5.0
            
            # Add a subtitle for the title slide
            title_item = SubRipItem(
                index=1,
                start=self._seconds_to_time(0),
                end=self._seconds_to_time(title_duration),
                text="<font size=\"16\" color=\"#ffffff\">[Title]</font>"
            )
            subs.append(title_item)
            
            # Start scene subtitles after title
            current_time += title_duration
            
            for i, (scene, duration) in enumerate(zip(scenes, durations)):
                # Get text based on language
                if is_dutch:
                    text = scene.get('text_nl', '')
                    color = "#ffffff"  # White for Dutch
                    size = "18"  # Smaller font size
                else:
                    text = scene.get('text_en', '')
                    color = "#add8e6"  # Light blue for English
                    size = "16"  # Even smaller for English
                
                # Wrap text to avoid too long lines
                wrapped_lines = textwrap.wrap(text.strip(), width=40 if is_dutch else 45)
                
                # Add font styling to each line
                styled_lines = [f"<font size=\"{size}\" color=\"{color}\">{line}</font>" for line in wrapped_lines]
                wrapped_text = '\n'.join(styled_lines)
                
                # Calculate start and end times
                start_time = current_time
                end_time = start_time + duration
                
                # Create subtitle item
                item = SubRipItem(
                    index=i+2,  # +2 because we already added the title subtitle
                    start=self._seconds_to_time(start_time),
                    end=self._seconds_to_time(end_time),
                    text=wrapped_text
                )
                subs.append(item)
                
                current_time = end_time
                
            # Save subtitle file
            subs.save(output_file, encoding='utf-8')
            return True
            
        except Exception as e:
            logger.error(f"Error creating subtitles: {e}")
            return False
            
    def _seconds_to_time(self, seconds):
        """Convert seconds to SRT time format"""
        try:
            from datetime import timedelta
            
            td = timedelta(seconds=seconds)
            hours, remainder = divmod(td.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            milliseconds = int(td.microseconds / 1000)
            
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        except Exception as e:
            logger.error(f"Error converting seconds to time: {e}")
            return "00:00:00,000"
    
    def _ensure_audio_in_video(self, video_file, audio_file, output_file):
        """Use ffmpeg to ensure audio is correctly attached to video"""
        try:
            if not self.ffmpeg_path:
                logger.warning("ffmpeg not available, cannot ensure audio attachment")
                return video_file
                
            logger.info("Ensuring audio is correctly attached to video")
            ffmpeg_cmd = [
                self.ffmpeg_path, 
                "-i", video_file, 
                "-i", audio_file,
                "-c:v", "copy", 
                "-c:a", "aac", 
                "-map", "0:v", 
                "-map", "1:a", 
                "-shortest",
                output_file
            ]
            
            subprocess.run(ffmpeg_cmd, check=True)
            return output_file
        except Exception as e:
            logger.error(f"Error ensuring audio attachment: {e}")
            return video_file  # Return original video if operation fails
            
    async def create_story_video(self, story_data):
        """Create a video with DALL-E generated images, narration, and subtitles"""
        try:
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            base_filename = f"story_{timestamp}"
            
            nl_audio_file = os.path.join(self.temp_dir, f"{base_filename}_nl.mp3")
            nl_subs_file = os.path.join(self.temp_dir, f"{base_filename}_nl.srt")
            en_subs_file = os.path.join(self.temp_dir, f"{base_filename}_en.srt")
            output_file = os.path.join(self.temp_dir, f"{base_filename}.mp4")
            audio_fixed_file = os.path.join(self.temp_dir, f"{base_filename}_audio_fixed.mp4")
            output_with_subs = os.path.join(self.temp_dir, f"{base_filename}_with_subs.mp4")
            
            # Extract all Dutch text for narration
            all_text_nl = []
            for scene in story_data['scenes']:
                all_text_nl.append(scene.get('text_nl', ''))
            
            # Generate Dutch audio narration
            logger.info("Generating Dutch audio narration")
            nl_text = '\n\n'.join(all_text_nl)
            if not self._text_to_speech(nl_text, 'nl', nl_audio_file):
                raise Exception("Failed to generate Dutch audio")
                
            # Generate images for each scene using DALL-E
            logger.info("Generating DALL-E images for scenes")
            scene_clips = []
            scene_image_files = []
            
            # Create title image
            title_image = Image.new('RGB', (1024, 1024), (0, 0, 0))
            draw = ImageDraw.Draw(title_image)
            
            try:
                title_font = ImageFont.truetype("arial.ttf", 60)
            except:
                title_font = ImageFont.load_default()
                
            title_text = f"{story_data['title_nl']}\n{story_data['title_en']}"
            
            # Center title text
            title_position = (512 - 200, 512 - 50)  # Rough center estimate
            draw.text(title_position, title_text, font=title_font, fill=(255, 255, 255))
            
            title_image_file = os.path.join(self.temp_dir, f"{base_filename}_title.jpg")
            title_image.save(title_image_file)
            scene_image_files.append(title_image_file)
            
            title_clip = ImageClip(title_image_file).set_duration(5)
            scene_clips.append(title_clip)
            
            # Generate and process scene images
            for i, scene in enumerate(story_data['scenes']):
                logger.info(f"Processing scene {i+1}/{len(story_data['scenes'])}")
                
                # Generate image with DALL-E
                image_prompt = scene.get('image_prompt', '')
                image = await self.generate_image(image_prompt)
                
                if image is None:
                    # Create a fallback image if DALL-E generation fails
                    logger.warning(f"Using fallback image for scene {i+1}")
                    image = Image.new('RGB', (1024, 1024), (25, 25, 112))
                    draw = ImageDraw.Draw(image)
                    draw.text((50, 50), f"Scene {i+1}", fill=(255, 255, 255))
                    draw.text((50, 150), image_prompt[:500], fill=(255, 255, 255))
                
                # Add both Dutch and English text overlays to image
                text_nl = scene.get('text_nl', '')
                text_en = scene.get('text_en', '')
                scene_title = f"Scene {i+1}"
                image_with_text = self._add_text_to_image(image, text_nl, text_en, scene_title)
                
                # Save the image
                scene_image_file = os.path.join(self.temp_dir, f"{base_filename}_scene_{i}.jpg")
                image_with_text.save(scene_image_file)
                scene_image_files.append(scene_image_file)
                
                # Add a small delay between API calls to avoid rate limits
                await asyncio.sleep(0.5)
            
            # Get audio duration
            audio_clip = AudioFileClip(nl_audio_file)
            total_audio_duration = audio_clip.duration
            
            # Calculate duration for each scene based on text length
            scene_durations = []
            total_text_length = sum(len(scene.get('text_nl', '')) for scene in story_data['scenes'])
            
            for scene in story_data['scenes']:
                # Allocate time proportionally to text length
                text_length = len(scene.get('text_nl', ''))
                if total_text_length > 0:
                    duration = (text_length / total_text_length) * total_audio_duration
                else:
                    duration = total_audio_duration / len(story_data['scenes'])
                    
                # Ensure minimum duration
                duration = max(duration, 5.0)
                scene_durations.append(duration)
            
            # Create clips for each scene with their calculated durations
            scene_video_clips = []
            scene_video_clips.append(title_clip)  # Add title clip first
            
            for i, duration in enumerate(scene_durations):
                if i < len(scene_image_files) - 1:  # Skip title image
                    scene_clip = ImageClip(scene_image_files[i+1]).set_duration(duration)
                    scene_video_clips.append(scene_clip)
            
            # Concatenate all clips
            logger.info("Concatenating clips")
            final_video = concatenate_videoclips(scene_video_clips)
            
            # Add audio - this method sometimes has issues
            logger.info("Adding audio")
            try:
                final_video = final_video.set_audio(audio_clip)
            except Exception as e:
                logger.error(f"Error setting audio with MoviePy: {e}")
                # We'll fix this with ffmpeg later
            
            # Write video file
            logger.info(f"Writing video file to {output_file}")
            # Use safe settings to avoid ImageMagick issues
            final_video.write_videofile(
                output_file, 
                codec='libx264', 
                audio_codec='aac', 
                fps=24,
                temp_audiofile=os.path.join(self.temp_dir, f"{base_filename}_temp_audio.m4a"),
                remove_temp=True,
                audio_bitrate="128k",
                preset="ultrafast",
                threads=2
            )
            
            # Fix audio attachment with ffmpeg if needed
            if self.ffmpeg_path:
                fixed_video = self._ensure_audio_in_video(output_file, nl_audio_file, audio_fixed_file)
            else:
                fixed_video = output_file
                
            # Create subtitle files after we know the final durations
            logger.info("Creating subtitle files with styling")
            self._create_subtitles(story_data['scenes'], nl_subs_file, scene_durations, is_dutch=True)  # Dutch subtitles
            self._create_subtitles(story_data['scenes'], en_subs_file, scene_durations, is_dutch=False)  # English subtitles
            
            # Embed subtitles using ffmpeg if available
            if self.ffmpeg_path:
                logger.info("Embedding subtitles with ffmpeg")
                try:
                    ffmpeg_cmd = [
                        self.ffmpeg_path, 
                        "-i", fixed_video, 
                        "-i", nl_subs_file, 
                        "-i", en_subs_file,
                        "-map", "0:v", 
                        "-map", "0:a", 
                        "-map", "1", 
                        "-map", "2",
                        "-c:v", "copy", 
                        "-c:a", "copy",
                        "-c:s", "mov_text",
                        "-metadata:s:s:0", "language=nl",
                        "-metadata:s:s:1", "language=en",
                        output_with_subs
                    ]
                    
                    subprocess.run(ffmpeg_cmd, check=True)
                    video_to_return = output_with_subs
                except Exception as e:
                    logger.error(f"Error embedding subtitles: {e}")
                    # Return the video without subtitles if embedding fails
                    video_to_return = fixed_video
            else:
                logger.warning("ffmpeg not available, returning video without embedded subtitles")
                video_to_return = fixed_video
            
            # Clean up temporary image files
            for image_file in scene_image_files:
                if os.path.exists(image_file):
                    try:
                        os.remove(image_file)
                    except Exception as e:
                        logger.warning(f"Could not remove temporary image file {image_file}: {e}")
            
            # Don't remove the original video file if we couldn't create the subtitled version
            if self.ffmpeg_path and os.path.exists(output_file) and os.path.exists(output_with_subs):
                try:
                    os.remove(output_file)
                    if os.path.exists(audio_fixed_file):
                        os.remove(audio_fixed_file)
                except:
                    pass
            
            return video_to_return
            
        except Exception as e:
            logger.error(f"Error creating story video: {e}")
            raise
            
    def cleanup_old_files(self, max_age_hours=24):
        """Clean up old temporary files"""
        try:
            current_time = time.time()
            count = 0
            
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                
                # Skip if it's a directory
                if os.path.isdir(file_path):
                    continue
                    
                # Check file age
                file_age_hours = (current_time - os.path.getmtime(file_path)) / 3600
                
                if file_age_hours > max_age_hours:
                    try:
                        os.remove(file_path)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Could not remove old file {file_path}: {e}")
            
            logger.info(f"Cleaned up {count} old files from {self.temp_dir}")
            
        except Exception as e:
            logger.error(f"Error cleaning up old files: {e}")