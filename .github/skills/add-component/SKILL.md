---
name: add-component
description: Add a new React component with Material UI
---

# Add Component Skill

Add React components to `apps/artagent/frontend/src/components/`.

## Component Template

```jsx
/**
 * ComponentName
 * Brief description of what this component does.
 */

import { memo, useCallback, useState } from 'react';
import { Box, Typography, Button } from '@mui/material';

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const ComponentName = memo(function ComponentName({ prop1, prop2, onAction }) {
  const [state, setState] = useState(null);

  const handleAction = useCallback(() => {
    onAction?.(state);
  }, [onAction, state]);

  return (
    <Box
      sx={{
        p: 2,
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      <Typography variant="h6">{prop1}</Typography>
      <Button onClick={handleAction} variant="contained">
        Action
      </Button>
    </Box>
  );
});

export default ComponentName;
```

## Steps

1. Create file in `src/components/ComponentName.jsx`
2. Import required MUI components
3. Use `memo()` for performance optimization
4. Use `useCallback()` for event handlers
5. Apply `sx` prop for styling with theme values
6. Export as default

## Styling with `sx` Prop

```jsx
// Theme spacing: p: 2 = 16px (8px * 2)
<Box
  sx={{
    p: 2,
    mt: 1,
    bgcolor: 'background.paper',
    borderRadius: 1,
    display: 'flex',
    gap: 2,
  }}
/>

// Responsive values
<Stack
  direction={{ xs: 'column', sm: 'row' }}
  spacing={{ xs: 1, sm: 2, md: 4 }}
/>
```

## Common MUI Imports

```jsx
// Layout
import { Box, Stack, Container, Grid } from '@mui/material';

// Inputs
import { TextField, Button, IconButton } from '@mui/material';

// Display
import { Typography, List, Chip, Avatar } from '@mui/material';

// Feedback
import { Dialog, Snackbar, Alert, CircularProgress } from '@mui/material';

// Icons
import { Send, Mic, Settings, Close } from '@mui/icons-material';
```

## Accessibility

```jsx
// Always add aria-label to icon buttons
<IconButton aria-label="Send message" onClick={handleSend}>
  <SendIcon />
</IconButton>

// Use semantic HTML via component prop
<Typography component="h1" variant="h4">
  Page Title
</Typography>
```

## Props Pattern

```jsx
// Destructure with defaults
const Component = ({
  title = 'Default',
  isLoading = false,
  onSubmit,
  children,
}) => { ... };
```

## Hook Extraction

For complex logic, create custom hook in `hooks/`:

```jsx
// hooks/useComponentLogic.js
export const useComponentLogic = (initialValue) => {
  const [value, setValue] = useState(initialValue);
  const handleChange = useCallback((newValue) => {
    setValue(newValue);
  }, []);
  return { value, handleChange };
};
```
