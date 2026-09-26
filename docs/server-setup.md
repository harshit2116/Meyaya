# Server setup and dashboard

Members with **Manage Server** can use either slash commands or the server's written prefix.

- `/serversetup` or `uwu serversetup` opens a guided menu. Choose one chat channel or the entire server, then select automatic replies and moderation features. Review and save to apply the choices together. Cancel or let the menu expire to leave the server unchanged.
- `/serverdashboard` or `uwu serverdashboard` shows the existing daily message allowance, messages used and remaining, reset time, commands completed today, chat settings, and moderation switches.

The setup includes 3-day newcomer probation, cross-channel repeated text/image protection, and other-server invite blocking. Moderation requires Manage Messages in the affected channels. It does not enable a raid lockdown or English-only monitoring; those retain their separate commands.

Chat channel restrictions cover mentions, replies, and automatic replies, not ordinary commands. A selected channel does not include its threads. Automatic replies use the same existing server allowance. Setup never changes the quota or command prefix.

The dashboard's top three members are ranked by submitted chat requests in the last 7 days, using existing logs. Requests can include failed replies; this is not an all-time successful-conversation count. It does not display message contents or activity from other servers. Exempt servers display an unlimited allowance.

Slash setup and dashboard responses are private to the manager. Prefix responses appear in the channel, but only the manager who opened setup can operate it. Only server managers can run either command.

Member options are named `member1`, `member2`, etc. throughout slash commands and help examples. Written commands still take mentions positionally, such as `uwu ship @Haru @Ruru`; do not type the parameter labels literally.
