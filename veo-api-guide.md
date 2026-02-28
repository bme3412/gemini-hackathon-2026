Nano Banana 2 is here. Learn more in our blog.
Home
Gemini API
Docs
Generate videos with Veo 3.1 in Gemini API



To learn about video understanding, see the Video understanding guide.

Veo 3.1 is Google's state-of-the-art model for generating high-fidelity, 8-second 720p, 1080p or 4k videos featuring stunning realism and natively generated audio. You can access this model programmatically using the Gemini API. To learn more about the available Veo model variants, see the Model Versions section.

Veo 3.1 excels at a wide range of visual and cinematic styles and introduces several new capabilities:

Portrait videos: Choose between landscape (16:9) and portrait (9:16) videos.
Video extension: Extend videos that were previously generated using Veo.
Frame-specific generation: Generate a video by specifying the first and/or last frames.
Image-based direction: Use up to three reference images to guide the content of your generated video.
For more information about writing effective text prompts for video generation, see the Veo prompt guide

Text to video generation
Choose an example to see how to generate a video with dialogue, cinematic realism, or creative animation:

Dialogue & Sound Effects Cinematic Realism Creative Animation

Python
JavaScript
Go
Java
REST

import time
from google import genai
from google.genai import types

client = genai.Client()

prompt = """A close up of two people staring at a cryptic drawing on a wall, torchlight flickering.
A man murmurs, 'This must be it. That's the secret code.' The woman looks at him and whispering excitedly, 'What did you find?'"""

operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt=prompt,
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the generated video.
generated_video = operation.response.generated_videos[0]
client.files.download(file=generated_video.video)
generated_video.video.save("dialogue_example.mp4")
print("Generated video saved to dialogue_example.mp4")


Control the aspect ratio
Veo 3.1 lets you create landscape (16:9, the default setting) or portrait (9:16) videos. You can tell the model which one you want using the aspect_ratio parameter:

Python
JavaScript
Go
REST

import time
from google import genai
from google.genai import types

client = genai.Client()

prompt = """A montage of pizza making: a chef tossing and flattening the floury dough, ladling rich red tomato sauce in a spiral, sprinkling mozzarella cheese and pepperoni, and a final shot of the bubbling golden-brown pizza, upbeat electronic music with a rhythmical beat is playing, high energy professional video."""

operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt=prompt,
    config=types.GenerateVideosConfig(
      aspect_ratio="9:16",
    ),
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the generated video.
generated_video = operation.response.generated_videos[0]
client.files.download(file=generated_video.video)
generated_video.video.save("pizza_making.mp4")
print("Generated video saved to pizza_making.mp4")


Control the resolution
Veo 3.1 can also directly generate 720p, 1080p or 4k videos.

Note that the higher the resolution, the higher the latency will be. 4k videos are also more pricey (cf. pricing).

Video extension is also limited to 720p videos.

Python
JavaScript
Go
REST

import time
from google import genai
from google.genai import types

client = genai.Client()

prompt = """A stunning drone view of the Grand Canyon during a flamboyant sunset that highlights the canyon's colors. The drone slowly flies towards the sun then accelerates, dives and flies inside the canyon."""

operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt=prompt,
    config=types.GenerateVideosConfig(
      resolution="4k",
    ),
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the generated video.
generated_video = operation.response.generated_videos[0]
client.files.download(file=generated_video.video)
generated_video.video.save("4k_grand_canyon.mp4")
print("Generated video saved to 4k_grand_canyon.mp4")


Image to video generation
The following code demonstrates generating an image using Gemini 2.5 Flash Image aka Nano Banana, then using that image as the starting frame for generating a video with Veo 3.1.

Python
JavaScript
Go
Java

import time
from google import genai

client = genai.Client()

prompt = "Panning wide shot of a calico kitten sleeping in the sunshine"

# Step 1: Generate an image with Nano Banana.
image = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=prompt,
    config={"response_modalities":['IMAGE']}
)

# Step 2: Generate video with Veo 3.1 using the image.
operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt=prompt,
    image=image.parts[0].as_image(),
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the video.
video = operation.response.generated_videos[0]
client.files.download(file=video.video)
video.video.save("veo3_with_image_input.mp4")
print("Generated video saved to veo3_with_image_input.mp4")
Using reference images
Note: This feature is available for Veo 3.1 models only.
Veo 3.1 now accepts up to 3 reference images to guide your generated video's content. Provide images of a person, character, or product to preserve the subject's appearance in the output video.

For example, using these three images generated with Nano Banana as references with a well-written prompt creates the following video:

`dress_image`	`woman_image`	`glasses_image`
High-fashion flamingo dress with layers of pink and fuchsia feathers	Beautiful woman with dark hair and warm brown eyes	Whimsical pink, heart-shaped sunglasses
Python
JavaScript
Go
REST

import time
from google import genai

client = genai.Client()

prompt = "The video opens with a medium, eye-level shot of a beautiful woman with dark hair and warm brown eyes. She wears a magnificent, high-fashion flamingo dress with layers of pink and fuchsia feathers, complemented by whimsical pink, heart-shaped sunglasses. She walks with serene confidence through the crystal-clear, shallow turquoise water of a sun-drenched lagoon. The camera slowly pulls back to a medium-wide shot, revealing the breathtaking scene as the dress's long train glides and floats gracefully on the water's surface behind her. The cinematic, dreamlike atmosphere is enhanced by the vibrant colors of the dress against the serene, minimalist landscape, capturing a moment of pure elegance and high-fashion fantasy."

dress_reference = types.VideoGenerationReferenceImage(
  image=dress_image, # Generated separately with Nano Banana
  reference_type="asset"
)

sunglasses_reference = types.VideoGenerationReferenceImage(
  image=glasses_image, # Generated separately with Nano Banana
  reference_type="asset"
)

woman_reference = types.VideoGenerationReferenceImage(
  image=woman_image, # Generated separately with Nano Banana
  reference_type="asset"
)

operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt=prompt,
    config=types.GenerateVideosConfig(
      reference_images=[dress_reference, glasses_reference, woman_reference],
    ),
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the video.
video = operation.response.generated_videos[0]
client.files.download(file=video.video)
video.video.save("veo3.1_with_reference_images.mp4")
print("Generated video saved to veo3.1_with_reference_images.mp4")


Using first and last frames
Note: This feature is available for Veo 3.1 models only
Veo 3.1 lets you create videos using interpolation, or specifying the first and last frames of the video. For information about writing effective text prompts for video generation, see the Veo prompt guide.

Python
JavaScript
Go
REST

import time
from google import genai

client = genai.Client()

prompt = "A cinematic, haunting video. A ghostly woman with long white hair and a flowing dress swings gently on a rope swing beneath a massive, gnarled tree in a foggy, moonlit clearing. The fog thickens and swirls around her, and she slowly fades away, vanishing completely. The empty swing is left swaying rhythmically on its own in the eerie silence."

operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt=prompt,
    image=first_image, # The starting frame is passed as a primary input
    config=types.GenerateVideosConfig(
      last_frame=last_image # The ending frame is passed as a generation constraint in the config
    ),
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the video.
video = operation.response.generated_videos[0]
client.files.download(file=video.video)
video.video.save("veo3.1_with_interpolation.mp4")
print("Generated video saved to veo3.1_with_interpolation.mp4")
`first_image`	`last_image`	veo3.1_with_interpolation.mp4
A ghostly woman with long white hair and a flowing dress swings gently on a rope swing	The ghostly woman vanishes from the swing	A cinematic, haunting video of an eerie woman disappearing from a swing in the mist
Extending Veo videos
Note: This feature is available for Veo 3.1 models only
Use Veo 3.1 to extend videos that you previously generated with Veo by 7 seconds and up to 20 times.

Input video limitations:

Veo-generated videos only up to 141 seconds long.
Gemini API only supports video extensions for Veo-generated videos.
The video should come from a previous generation, like operation.response.generated_videos[0].video
Videos are stored for 2 days, but if a video is referenced for extension, its 2-day storage timer resets. You can only extend videos that were generated or referenced in the last two days.
Input videos are expected to have a certain length, aspect ratio, and dimensions:
Aspect ratio: 9:16 or 16:9
Resolution: 720p
Video length: 141 seconds or less
The output of the extension is a single video combining the user input video and the generated extended video for up to 148 seconds of video.

This example takes the a Veo-generated video, shown here with its original prompt, and extends it using the video parameter and a new prompt:

Prompt	Output: butterfly_video
An origami butterfly flaps its wings and flies out of the french doors into the garden.	Origami butterfly flaps its wings and flies out of the french doors into the garden.
Python
JavaScript
Go
REST

import time
from google import genai

client = genai.Client()

prompt = "Track the butterfly into the garden as it lands on an orange origami flower. A fluffy white puppy runs up and gently pats the flower."

operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    video=operation.response.generated_videos[0].video, # This must be a video from a previous generation
    prompt=prompt,
    config=types.GenerateVideosConfig(
        number_of_videos=1,
        resolution="720p"
    ),
)

# Poll the operation status until the video is ready.
while not operation.done:
    print("Waiting for video generation to complete...")
    time.sleep(10)
    operation = client.operations.get(operation)

# Download the video.
video = operation.response.generated_videos[0]
client.files.download(file=video.video)
video.video.save("veo3.1_extension.mp4")
print("Generated video saved to veo3.1_extension.mp4")


For information about writing effective text prompts for video generation, see the Veo prompt guide.

Handling asynchronous operations
Video generation is a computationally intensive task. When you send a request to the API, it starts a long-running job and immediately returns an operation object. You must then poll until the video is ready, which is indicated by the done status being true.

The core of this process is a polling loop, which periodically checks the job's status.

Python
JavaScript
Go
Java
REST

import time
from google import genai
from google.genai import types

client = genai.Client()

# After starting the job, you get an operation object.
operation = client.models.generate_videos(
    model="veo-3.1-generate-preview",
    prompt="A cinematic shot of a majestic lion in the savannah.",
)

# Alternatively, you can use operation.name to get the operation.
operation = types.GenerateVideosOperation(name=operation.name)

# This loop checks the job status every 10 seconds.
while not operation.done:
    time.sleep(10)
    # Refresh the operation object to get the latest status.
    operation = client.operations.get(operation)

# Once done, the result is in operation.response.
# ... process and download your video ...
Veo API parameters and specifications
These are the parameters you can set in your API request to control the video generation process.

Parameter	Description	Veo 3.1 & Veo 3.1 Fast	Veo 3 & Veo 3 Fast	Veo 2
prompt	The text description for the video. Supports audio cues.	string	string	string
negativePrompt	Text describing what not to include in the video.	string	string	string
image	An initial image to animate.	Image object	Image object	Image object
lastFrame	The final image for an interpolation video to transition. Must be used in combination with the image parameter.	Image object	Image object	Image object
referenceImages	Up to three images to be used as style and content references.	VideoGenerationReferenceImage object (Veo 3.1 only)	n/a	n/a
video	Video to be used for video extension.	Video object from a previous generation	n/a	n/a
aspectRatio	The video's aspect ratio.	"16:9" (default),
"9:16"

"16:9" (default),
"9:16"	"16:9" (default),
"9:16"
resolution	The video's aspect ratio.	"720p" (default),
"1080p" (only supports 8s duration),
"4k" (only supports 8s duration)

"720p" only for extension	"720p" (default),
"1080p" (only supports 8s duration),
"4k" (only supports 8s duration)

"720p" only for extension	Unsupported
durationSeconds	Length of the generated video.	"4", "6", "8".

Must be "8" when using extension, reference images or with 1080p and 4k resolutions	"4", "6", "8".

Must be "8" when using extension, reference images or with 1080p and 4k resolutions	"5", "6", "8"
personGeneration	Controls the generation of people.
(See Limitations for region restrictions)	Text-to-video & Extension:
"allow_all" only
Image-to-video, Interpolation, & Reference images:
"allow_adult" only	Text-to-video:
"allow_all" only
Image-to-video:
"allow_adult" only	Text-to-video:
"allow_all", "allow_adult", "dont_allow"
Image-to-video:
"allow_adult", and "dont_allow"
Note that the seed parameter is also available for Veo 3 models. It doesn't guarantee determinism, but slightly improves it.

You can customize your video generation by setting parameters in your request. For example you can specify negativePrompt to guide the model.

Python
JavaScript
Go
