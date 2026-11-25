# WhatsApp panel: what to fix

Checked on 25 Nov 2026 by reading the panel's code. The live panel was not tried.
**List 1 is in the code since 25 Nov 2026** (88 checks on a throwaway database), installed on the local panel (14:33), with an eye to show and hide passwords;
its "Now" column is how it was before. Lists 2 and 3 are not done. All of list 1 is inside `whatsapp_panel` only: no Odoo module
changes, no new database table, and messages are sent as before.

## 1. Main fixes (in the code)

| # | What | Now | After the fix |
|---|---|---|---|
| 1 | Remove server | On the server's page no question is asked; its databases, keys and client logins are deleted | Asks first and says how many databases go with it |
| 2 | Server address | Can be saved empty or mistyped, then its databases are refused | An empty or invalid address, or one already registered, is refused with the reason |
| 3 | Deactivate on the home list | Stops all numbers and e-mail without asking | Asks first |
| 4 | Change vendor | Drops all the numbers on Save, only a small note | Asks first, nothing is saved without a yes |
| 5 | Activity | Most removals and key resets are not recorded | Records what was done and by which login |
| 6 | Remove a number | Hidden under More; none when it is the only number | A visible Remove beside Turn off, also for the only number. Then the database, its key, login and e-mail stay |
| 7 | Turned-off vendor | Can still sign in, and so can its clients | Neither can sign in; those signed in are out on the next page |
| 8 | Wrong passwords | No limit | After 5 wrong tries a wait of 1 minute, growing to 15 |
| 9 | Password reset | Whoever used the old password stays signed in | They are signed out |
| 10 | Client pages | Opt-outs link only goes home; Activity shows one number; another number's opt-out cannot be removed | The link opens the list, Activity shows all the client's numbers, Remove works |
| 11 | Account page | A too short new password says "Current password is wrong" | Says the new password needs at least 6 characters |

Order: 1 to 5, then 6, then 7 to 9 (sign-in, tested with most care), then 10 and 11.

## 2. Useful, can wait

| # | What | Note |
|---|---|---|
| 1 | Alert when a number disconnects | Done in WA Tracker 1.5.5 (Owner Numbers), looked at once a minute. Within seconds: not built |
| 2 | Test WhatsApp message button | Today only e-mail has a test of its connection |
| 3 | Search, and dates in Activity | Activity shows the last 200 lines only |
| 4 | Delete a vendor login | Today: add, or reset the password |
| 5 | Page for e-mail unsubscribes | They block e-mail but no page shows them. They should count for the whole database, not one key |
| 6 | Restart a connected number | The button shows only when it is not connected. Check it against the QR fix (c733fd2) before building |

## 3. Leave as it is

| # | What | Why |
|---|---|---|
| 1 | Delete on the Numbers list | The number's own page has it; taking it out of databases first is a good safety step |
| 2 | Forgot password | The administrator resets a vendor's; the vendor or administrator a client's; the administrator's own from the command line |
| 3 | Second administrator | Needed only if two people run the panel |
| 4 | Rename a vendor login | Add a new one; delete the old one once list 2, number 4 is built |
| 5 | Remove an e-mail account | The off tick is enough |
| 6 | Export of Activity | Nobody has asked for it |
| 7 | Send a real test e-mail | Test connection already checks the mail server |

## Before going live

1. Test on a separate copy, not on the live panel.
2. Back up the live panel `C:/whatsapp_server/panel` **and** its database. `whatsapp_panel_25112026_2.zip`,
   beside this folder, holds the code of this folder only.
3. `server.js` is committed up to c733fd2 (the QR never starts a second link; a number turned off
   from Odoo may still ask and add). The fixes are made on that version. Leave the QR part as it is and
   never put an older `server.js` back. Look first whether the live panel has that version: if not,
   it goes live together with these fixes.
4. Look whether any vendor is off today: with number 7 it can no longer sign in.
5. Restart at a quiet time. Odoo cannot send for some seconds, a message arriving just then could
   be missed, and everyone signs in to the panel again. Check that the panel started again.
6. To go back: put the old panel files back and restart. What was removed meanwhile stays removed.
