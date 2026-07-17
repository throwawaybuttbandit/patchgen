# chisel

generates a .patch file that fixes broken ea25 mods.
### here is the [web ui](https://chisel.ftp.sh), if you don't want to do all of the steps below.
mirror: https://rfpatcher.pages.dev/


## install and use

```sh
$ # python -m venv .venv 
$ pip install -r requirements.txt # --break-system-packages -> if you dont wanna venv
$ python main.py foo.rfc
```

a .patch file will be generated in the same directory. you can also (obviously) optionally glob a directory of rfcs to do mass patches:
```sh
$ python main.py ./mods/*.rfc
```

drop the generated patchfile next to the workshop folder.

## how does this work
ravenfield's `PatchData` loads a file of the form:
```cs
lzf.compress(utf8(JsonUtility.ToJson(dat)))
```

where `PatchData` looks something like this:

```json 
{
  "version": 26,
  "animationDatabase": {
    "patchedAnimations": [
      {
        "controllerName": "<AnimatorController name>",
        "clipName": "<AnimationClip name>",
        "frameRate": 60.0,
        "wrapMode": 0,
        "curves": [
          { "relativePath": "Armature/Arm_L",
            "propertyName": "localRotation.x",
            "times":  [ /* int = round(seconds * 100000) */ ],
            "values": [ /* int = round(value   * 100000) */ ] }
          // ...localPosition.{x,y,z}, localScale.{x,y,z}, localRotation.{x,y,z,w}, blah blah
        ]
      }
    ]
  }
}
```

then the game rebuilds a "Legacy" AnimationClip from these curves, and play that instead of the broken one.

for some ea25 weapons mod, the anims live in each `AnimationClip`'s baked muscle clip (`m_MuscleClip`, `StreamedClip`, `DenseClip`, `ConstantClip`), addressed by something called a `m_ClipBindingConstant`. to produce the patchfile:
- decode the muscle clip into per-bone Transform curves. we get `localPosition`, `localScale` and Euler rotation data from the clip
- resolve each binding's CRC32 pathhash into a bone path
- convert the euler rotation to a ccq (continuity-corrected quaternion). this basically just does the resample curves fix lol
- then we encode and serialize it back to ravenfield's patch format. triv


(actual detailed writeup coming soon)
