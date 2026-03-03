### Readme Best Practices

Readme is for human users to understand how to install and run the project.
Goal is for a user to be able to read it in under a minute and get it up and running in 5 minutes
- Above all, keep it short and simple - focused on how to install and how to use
- No implementation details in Readme
- Focus on the happy-path case, don't describe theoretical error cases or alternative installation instructions
- Don't describe how to use common tools (like screen, poetry, bash etc)
- No code in Readme. Command line commands are ok and should use concrete, copy-pasteable commands
- Don't describe migration, backups or debugging in the Readme
- Don't describe legacy features in the Readme. It should only document the state of code base NOW. Nothing about the past.
- If there are extended docs, dont reference them in the Readme. Users can find them on their own.


### Arch Docs Best Practices

Arch docs are located at docs/architecture
These docs are supposed to set architecture guidelines for their respective areas, as well as serving as a quick reference of the design.
Do not include code in these docs, the LLMs can read the code themselves.

