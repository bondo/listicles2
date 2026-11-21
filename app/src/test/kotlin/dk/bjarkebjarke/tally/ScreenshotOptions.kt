package dk.bjarkebjarke.tally

import com.dropbox.differ.SimpleImageComparator
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.ThresholdValidator

/**
 * M1-03: goldens match exactly. Roborazzi's defaults tolerate a colour distance, a shift of 2 pixels and 1 % changed
 * pixels, which would hide a changed colour or a moved label, so every screenshot test passes these options.
 * scripts/check_screenshots.py fails the build if a tolerance is set anywhere else or here is anything but zero.
 */
object ScreenshotOptions {
    val exact: RoborazziOptions =
        RoborazziOptions(
            compareOptions =
                RoborazziOptions.CompareOptions(
                    imageComparator = SimpleImageComparator(maxDistance = 0f, hShift = 0, vShift = 0),
                    resultValidator = ThresholdValidator(0f),
                ),
        )
}
