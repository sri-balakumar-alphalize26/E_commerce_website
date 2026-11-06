/** @odoo-module **/

/**
 * What the two enquiry alarms sound like, and who is currently sounding them.
 *
 * The tones live here rather than in the screen because the background
 * service rings the same two alarms from every other menu, and two copies of
 * a tone drift apart - at which point the counter has learned one alarm and
 * is hearing another.
 */

/** Lower and slower than the packing alarm, so the two never blur. */
export const ENQUIRY_TONE = { lo: 620, hi: 480, step: 0.75, len: 0.45 };

/**
 * The third alarm: two close notes, fast, like a phone that wants answering
 * - which is literally what it is asking for.
 */
export const STALLED_TONE = { lo: 880, hi: 990, step: 0.28, len: 0.22 };

/**
 * How many Enquiries screens are mounted in this tab.
 *
 * The screen and the background service would otherwise both ring the same
 * alarm at the same time, which is not twice as loud - it is two alarms
 * beating against each other. While the screen is open it owns the sound,
 * because the person is already looking at the thing that is ringing.
 */
/**
 * The fourth: waiting for stock that was bought in. Slow and low - it is a
 * morning reminder, not an emergency, and it must not be mistaken for the
 * packing alarm on the same screen.
 */
export const SUPPLY_TONE = { lo: 420, hi: 350, step: 1.1, len: 0.6 };

export const presence = { screens: 0 };
