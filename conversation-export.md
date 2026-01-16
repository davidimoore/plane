# Claude Code Conversation: Publishing Conversation Links

**Date:** 2026-01-16
**Repository:** davidimoore/plane
**Branch:** claude/shareable-conversation-export-hDW5g

---

## Summary

This conversation explored how to publish and share Claude Code conversations, uncovering the difference between local CLI features and web-based sharing capabilities.

---

## Key Findings

### Initial Misconception

Initially explored creating a `.claude_code/claude_code.json` configuration file for conversation publishing, but this approach was incorrect as **Claude Code CLI does not have a built-in conversation publishing feature**.

### The Correct Approach: Using the `&` Prefix

Claude Code supports sharing conversations through the **web version** using the `&` prefix:

```bash
& Create a shareable version of this conversation.
```

#### How the `&` Prefix Works

- Creates a new web session on claude.ai with current conversation context
- Runs tasks autonomously in the cloud
- Generates shareable links accessible to others
- Allows monitoring with `/tasks` command
- Supports teleporting between terminal and web with `/teleport`

#### Alternative Command

```bash
claude --remote "Your task here"
```

---

## Prerequisites for Sharing Conversations

### 1. Subscription Requirements

The `&` prefix and remote sessions require:
- Pro users
- Max users
- Team premium seat users
- Enterprise premium seat users

### 2. Setup Requirements

1. **Install the Claude GitHub App**
   - Visit: https://github.com/apps/claude/installations/new
   - Install on target repository

2. **Complete Onboarding**
   - Go to: https://claude.ai/code
   - Create a cloud environment:
     - Set environment name
     - Configure network access level
     - Add environment variables (if needed)

3. **Verify Setup**
   - Once environment is created, the `&` prefix will work
   - Can use `/remote-env` to select different environments

---

## Error Resolution

### "No environments available" Error

**Cause:** No cloud environment has been created through the web interface

**Solution:**
1. Visit https://claude.ai/code
2. Complete onboarding by creating at least one cloud environment
3. Configure environment settings as needed
4. Retry the `&` command

---

## Alternative Sharing Methods

Since the `&` prefix requires web setup, here are other options:

1. **Manual Export**: Copy/paste conversation content into documents or GitHub issues

2. **Session Resumption**:
   ```bash
   /rename session-name
   claude --resume session-name
   ```
   (Requires shared file system access)

3. **Structured Output**:
   ```bash
   claude -p "your query" --output-format json > conversation.json
   ```

4. **Git-based Sharing**: Commit code changes and share via pull requests

---

## Resources

- **Claude Code on the web documentation**: https://code.claude.com/docs/en/claude-code-on-the-web.md
- **GitHub App Installation**: https://github.com/apps/claude/installations/new
- **Web Interface**: https://claude.ai/code
- **Feedback**: https://github.com/anthropics/claude-code/issues

---

## Next Steps

To successfully share this conversation:

1. ✅ Claude GitHub app installed on repository
2. ⏳ Complete onboarding at https://claude.ai/code
3. ⏳ Create cloud environment
4. ⏳ Use `&` prefix to create shareable web session

Once setup is complete, any conversation can be shared by prefixing commands with `&`.
