package dk.bjarkebjarke.tally

import com.dropbox.differ.SimpleImageComparator
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.ThresholdValidator

/**
 * M1-03: goldens match exactly. Roborazzi's default options forgive a colour distance of 0.007 per pixel (a one-step
 * change in each of R, G and B passes), which would hide a changed colour token, so every capture passes these options.
 * scripts/check_screenshots.py fails the build when a capture leaves them out or a tolerance is set anywhere else.
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
