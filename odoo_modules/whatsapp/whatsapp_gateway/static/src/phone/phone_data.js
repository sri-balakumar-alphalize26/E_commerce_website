/** @odoo-module **/

// What every phone box shares: the countries, the digits rule, the split of saved values.
let countriesPromise = null;
let queue = null;
const known = {};

export function loadCountries(orm) {
    if (!countriesPromise) {
        countriesPromise = orm.silent.call("whatsapp.connect", "phone_countries", []).catch((err) => {
            countriesPromise = null;
            throw err;
        });
    }
    return countriesPromise;
}

/** {country, national, pretty} of a saved value; many boxes ask once together. */
export async function splitPhone(orm, value) {
    if (value in known) {
        return known[value];
    }
    if (!queue) {
        const mine = { values: new Set() };
        queue = mine;
        mine.done = Promise.resolve().then(async () => {
            queue = null;
            Object.assign(known, await orm.silent.call("whatsapp.connect", "phone_split", [[...mine.values]]));
        });
    }
    queue.values.add(value);
    try {
        await queue.done;
    } catch {
        return {};
    }
    return known[value] || {};
}

/** Digits only, without the code or a leading zero, never too many. */
export function cleanPhone(text, country, landline = false) {
    const digits = (text || "").replace(/[^0-9]/g, "");
    if (!country) {
        return digits.slice(0, 15);
    }
    const max = landline ? country.amax || country.max : country.max;
    let out = digits;
    if (out.length > max && out.startsWith(country.dial)) {
        out = out.slice(country.dial.length);
    }
    if (!country.zero) {
        out = out.replace(/^0+/, "");
    }
    return out.slice(0, max);
}

export function findCountries(all, typed) {
    const word = typed.trim().toLowerCase().replace(/^\+/, "");
    if (!word) {
        return all;
    }
    return all.filter((c) => c.name.toLowerCase().includes(word) || c.dial.startsWith(word) || c.code.toLowerCase() === word);
}
