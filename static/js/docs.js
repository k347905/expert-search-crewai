let currentTaskId = null;
let currentToken = null;

async function tryCreateTask() {
    try {
        const response = await fetch('/api/tasks', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                task: "Sample task: Analyze the current trends in AI technology"
            })
        });

        const data = await response.json();
        currentTaskId = data.task_id;
        currentToken = data.token;

        // Store the token in localStorage
        if (data.task_id && data.token) {
            localStorage.setItem(`task_token_${data.task_id}`, data.token);
        }

        document.getElementById('response').textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        document.getElementById('response').textContent = `Error: ${error.message}`;
    }
}

async function tryGetTask() {
    if (!currentTaskId || !currentToken) {
        document.getElementById('response').textContent = 'Please create a task first';
        return;
    }

    try {
        const response = await fetch(`/api/tasks/${currentTaskId}`, {
            headers: {
                'Authorization': currentToken
            }
        });

        const data = await response.json();
        document.getElementById('response').textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        document.getElementById('response').textContent = `Error: ${error.message}`;
    }
}