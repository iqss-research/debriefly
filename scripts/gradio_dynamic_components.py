import gradio as gr

with gr.Blocks() as demo:

    page_number_state = gr.State(0)

    @gr.render(inputs=[page_number_state])
    def render_count(page_number):
        boxes = []
        for i in range(page_number):
            box = gr.Textbox(key=i, label=f"Box {i}")
            boxes.append(box)

        def another_fn(page_number, *box_values):
            print(f"box_values: {box_values}")
            return page_number + 1

        another_btn.click(
            another_fn, inputs=[page_number_state] + boxes, outputs=page_number_state
        )

    another_btn = gr.Button("Another", render=True)

    demo.launch()
