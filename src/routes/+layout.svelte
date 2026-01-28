<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<svelte:head>
	<title>LabAuto - MATLAB Report Generator</title>
	<meta name="description" content="Automated MATLAB lab report generation using AI" />
</svelte:head>

{@render children()}

