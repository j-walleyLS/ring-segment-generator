"""
streamlit_app.py
Web application for generating ring segment DXF files and technical PDF drawings
"""

import streamlit as st
import math
import ezdxf
from ezdxf import units
import io
import zipfile
from datetime import datetime
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black, red
import tempfile
import os


# Page configuration
st.set_page_config(
    page_title="Ring Segment Generator",
    page_icon="📐",
    layout="wide"
)

# Custom CSS for professional styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        color: #1e3d59;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .unit-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .download-section {
        background-color: #e8f4f8;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin-top: 2rem;
    }
    </style>
""", unsafe_allow_html=True)


class RingSegmentGenerator:
    """Core generator class for ring segments."""
    
    @staticmethod
    def calculate_segment_geometry(inner_radius=None, outer_radius=None, depth=None,
                                  chord_length=None, arc_length=None, angle_degrees=None):
        """Calculate all geometry parameters for a ring segment."""
        
        # Validate and calculate radii
        if inner_radius is None and outer_radius is None:
            raise ValueError("Must specify at least one radius")
        
        if depth is not None:
            if inner_radius is not None:
                outer_radius = inner_radius + depth
            elif outer_radius is not None:
                inner_radius = outer_radius - depth
        elif inner_radius is None or outer_radius is None:
            raise ValueError("Must specify both radii or one radius with depth")
        
        if inner_radius >= outer_radius:
            raise ValueError("Inner radius must be less than outer radius")
        
        # Calculate angle based on input
        if angle_degrees is not None:
            angle_rad = math.radians(angle_degrees)
        elif chord_length is not None:
            # Use outer radius for chord calculation
            if chord_length > 2 * outer_radius:
                raise ValueError(f"Chord length {chord_length} exceeds diameter")
            angle_rad = 2 * math.asin(chord_length / (2 * outer_radius))
        elif arc_length is not None:
            # Use outer radius for arc calculation
            angle_rad = arc_length / outer_radius
        else:
            raise ValueError("Must specify angle, chord length, or arc length")
        
        return {
            'inner_radius': inner_radius,
            'outer_radius': outer_radius,
            'depth': outer_radius - inner_radius,
            'angle_rad': angle_rad,
            'angle_degrees': math.degrees(angle_rad),
            'inner_arc_length': inner_radius * angle_rad,
            'outer_arc_length': outer_radius * angle_rad,
            'inner_chord_length': 2 * inner_radius * math.sin(angle_rad / 2),
            'outer_chord_length': 2 * outer_radius * math.sin(angle_rad / 2),
        }
    
    @staticmethod
    def create_dxf_segment(geometry):
        """Create a DXF file with segment geometry."""
        doc = ezdxf.new('R2010')
        doc.units = units.MM
        msp = doc.modelspace()
        
        inner_radius = geometry['inner_radius']
        outer_radius = geometry['outer_radius']
        angle_rad = geometry['angle_rad']
        
        start_angle = 0
        end_angle = math.degrees(angle_rad)
        
        centre = (0, 0)
        
        # Draw arcs
        msp.add_arc(center=centre, radius=inner_radius,
                   start_angle=start_angle, end_angle=end_angle)
        msp.add_arc(center=centre, radius=outer_radius,
                   start_angle=start_angle, end_angle=end_angle)
        
        # Calculate endpoints
        p1 = (inner_radius, 0)
        p2 = (outer_radius, 0)
        p3 = (outer_radius * math.cos(angle_rad),
              outer_radius * math.sin(angle_rad))
        p4 = (inner_radius * math.cos(angle_rad),
              inner_radius * math.sin(angle_rad))
        
        # Draw radial lines
        msp.add_line(p1, p2)
        msp.add_line(p3, p4)
        
        # Save to temporary file then read back
        # (ezdxf doesn't support direct BytesIO writing in all versions)
        with tempfile.NamedTemporaryFile(suffix='.dxf', delete=False) as tmp:
            doc.saveas(tmp.name)
            tmp_path = tmp.name
        
        with open(tmp_path, 'rb') as f:
            dxf_content = f.read()
        
        os.unlink(tmp_path)
        
        return dxf_content
    
    @staticmethod
    def create_pdf_drawing(units_data, project_info):
        """Create PDF technical drawing with all units."""
        
        # Create temporary file for PDF
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        
        # Create canvas
        c = canvas.Canvas(temp_pdf.name, pagesize=landscape(A3))
        page_width, page_height = landscape(A3)
        
        # Draw title block
        RingSegmentGenerator._draw_title_block(c, page_width, page_height, project_info)
        
        # Calculate drawing area - give more space for units
        margin = 15 * mm
        title_block_width = 150 * mm
        title_block_height = 30 * mm
        
        drawing_width = page_width - (2 * margin) - title_block_width
        drawing_height = page_height - (2 * margin) - title_block_height
        
        # Arrange units in grid
        num_units = len(units_data)
        if num_units == 0:
            return None
        
        # Optimize grid layout based on number of units
        if num_units == 1:
            cols, rows = 1, 1
        elif num_units == 2:
            cols, rows = 2, 1
        elif num_units <= 4:
            cols, rows = 2, 2
        elif num_units <= 6:
            cols, rows = 3, 2
        elif num_units <= 9:
            cols, rows = 3, 3
        else:
            cols = min(4, math.ceil(math.sqrt(num_units)))
            rows = math.ceil(num_units / cols)
        
        cell_width = drawing_width / cols
        cell_height = drawing_height / rows
        
        for idx, unit in enumerate(units_data):
            row = idx // cols
            col = idx % cols
            
            # Center units in their cells
            x_offset = margin + (col * cell_width) + (cell_width / 2)
            y_offset = page_height - margin - (row * cell_height) - (cell_height / 2)
            
            # Make units larger - use more of available space
            max_dimension = min(cell_width * 0.85, cell_height * 0.85)
            
            RingSegmentGenerator._draw_unit_with_dimensions(
                c, unit, x_offset, y_offset, max_dimension
            )
        
        c.save()
        temp_pdf.close()
        
        # Read file content
        with open(temp_pdf.name, 'rb') as f:
            pdf_content = f.read()
        
        # Clean up temp file
        os.unlink(temp_pdf.name)
        
        return pdf_content
    
    @staticmethod
    def _draw_title_block(c, page_width, page_height, project_info):
        """Draw title block and border."""
        
        # Main border
        c.setStrokeColor(black)
        c.setLineWidth(2)
        c.rect(10 * mm, 10 * mm, page_width - 20 * mm, page_height - 20 * mm)
        
        # Inner border
        c.setLineWidth(1)
        c.rect(12 * mm, 12 * mm, page_width - 24 * mm, page_height - 24 * mm)
        
        # Title block
        title_x = page_width - 150 * mm - 10 * mm
        title_y = 10 * mm
        title_width = 150 * mm
        title_height = 30 * mm
        
        c.rect(title_x, title_y, title_width, title_height)
        c.line(title_x, title_y + 15 * mm, title_x + title_width, title_y + 15 * mm)
        c.line(title_x + 75 * mm, title_y, title_x + 75 * mm, title_y + title_height)
        
        # Labels and values
        c.setFont("Helvetica-Bold", 8)
        c.drawString(title_x + 5 * mm, title_y + 25 * mm, "Order Nr")
        c.drawString(title_x + 5 * mm, title_y + 20 * mm, "Customer Name")
        c.drawString(title_x + 5 * mm, title_y + 10 * mm, "Drawing Title")
        c.drawString(title_x + 5 * mm, title_y + 5 * mm, "Project Name")
        
        c.drawString(title_x + 80 * mm, title_y + 25 * mm, project_info['company'])
        c.drawString(title_x + 80 * mm, title_y + 10 * mm, "Drawing Number")
        c.drawString(title_x + 80 * mm, title_y + 5 * mm, datetime.now().strftime("%d/%m/%Y"))
        
        c.setFont("Helvetica", 10)
        c.drawString(title_x + 30 * mm, title_y + 25 * mm, project_info['order_number'])
        c.drawString(title_x + 30 * mm, title_y + 20 * mm, project_info['customer'])
        c.drawString(title_x + 30 * mm, title_y + 10 * mm, "Ring Segments")
        c.drawString(title_x + 30 * mm, title_y + 5 * mm, project_info['project'])
        
        # Disclaimer
        c.setFont("Helvetica", 6)
        disclaimer = ("ALL DIMENSIONS TO BE VERIFIED ON SITE. "
                     "ALL CONSTRUCTION DRAWINGS AND DIVERSIONS "
                     "FROM THE DESIGN TO BE APPROVED BY THE "
                     "CUSTOMER PRIOR TO CONSTRUCTION OR FABRICATION")
        c.drawString(15 * mm, 15 * mm, disclaimer)
    
    @staticmethod
    def _draw_unit_with_dimensions(c, unit, x_center, y_center, max_size):
        """Draw unit with dimensions in CAD style with horizontal chord."""
        
        geometry = unit['geometry']
        
        # Get dimensions
        inner_radius = geometry['inner_radius']
        outer_radius = geometry['outer_radius']
        angle_deg = geometry['angle_degrees']
        angle_rad = math.radians(angle_deg)
        
        # Calculate scale to fit the space
        chord_length = geometry['outer_chord_length']
        scale = max_size * 0.6 / max(chord_length, outer_radius * 2)
        
        # Scaled dimensions
        inner_r = inner_radius * scale
        outer_r = outer_radius * scale
        depth = (outer_radius - inner_radius) * scale
        
        c.saveState()
        c.translate(x_center, y_center)
        
        # Apply rotation to make chord horizontal - do this ONCE for everything
        rotation_angle = (180 - angle_deg) / 2
        c.rotate(rotation_angle)
        
        # Now draw everything in natural position (0 to angle_deg)
        # Calculate the four corner points
        p1_x = inner_r
        p1_y = 0
        p2_x = outer_r
        p2_y = 0
        p3_x = outer_r * math.cos(angle_rad)
        p3_y = outer_r * math.sin(angle_rad)
        p4_x = inner_r * math.cos(angle_rad)
        p4_y = inner_r * math.sin(angle_rad)
        
        # Draw the segment
        c.setStrokeColor(black)
        c.setLineWidth(1.5)
        
        path = c.beginPath()
        path.moveTo(p1_x, p1_y)
        
        # Start radial line
        path.lineTo(p2_x, p2_y)
        
        # Outer arc
        num_segments = 40
        for i in range(num_segments + 1):
            angle = angle_rad * i / num_segments
            x = outer_r * math.cos(angle)
            y = outer_r * math.sin(angle)
            path.lineTo(x, y)
        
        # End radial line
        path.lineTo(p4_x, p4_y)
        
        # Inner arc (reverse)
        for i in range(num_segments, -1, -1):
            angle = angle_rad * i / num_segments
            x = inner_r * math.cos(angle)
            y = inner_r * math.sin(angle)
            path.lineTo(x, y)
        
        path.close()
        c.drawPath(path, stroke=1, fill=0)
        
        # Add dimensions in natural position (before rotation was applied)
        c.setStrokeColor(red)
        c.setLineWidth(0.5)
        c.setFont("Helvetica", 8)
        
        dim_offset = 25
        
        # Radial dimensions at start (right side when horizontal)
        # Extension lines
        c.line(p1_x, p1_y, p1_x + dim_offset, p1_y)
        c.line(p2_x, p2_y, p2_x + dim_offset + 10, p2_y)
        
        # Depth dimension
        depth_dim_x = p2_x + dim_offset
        c.line(depth_dim_x, p1_y - 3, depth_dim_x, p1_y + 3)
        c.line(depth_dim_x, p2_y - 3, depth_dim_x, p2_y + 3)
        c.line(depth_dim_x, p1_y, depth_dim_x, p2_y)
        # Arrows
        c.line(depth_dim_x, p1_y, depth_dim_x - 2, p1_y + 3)
        c.line(depth_dim_x, p1_y, depth_dim_x + 2, p1_y + 3)
        c.line(depth_dim_x, p2_y, depth_dim_x - 2, p2_y - 3)
        c.line(depth_dim_x, p2_y, depth_dim_x + 2, p2_y - 3)
        
        # Depth text (vertical)
        c.saveState()
        c.translate(depth_dim_x + 10, (p1_y + p2_y) / 2)
        c.rotate(90)
        c.drawString(-10, -3, f"{geometry['depth']:.0f}")
        c.restoreState()
        
        # Chord dimensions at the end angle
        # Extension lines
        c.line(p3_x, p3_y, p3_x - dim_offset * math.sin(angle_rad), p3_y + dim_offset * math.cos(angle_rad))
        c.line(p4_x, p4_y, p4_x - (dim_offset + 10) * math.sin(angle_rad), p4_y + (dim_offset + 10) * math.cos(angle_rad))
        
        # Outer chord
        chord_offset_x = -dim_offset * math.sin(angle_rad)
        chord_offset_y = dim_offset * math.cos(angle_rad)
        c.line(p2_x + chord_offset_x - 5 * math.cos(angle_rad), 
               p2_y + chord_offset_y - 5 * math.sin(angle_rad),
               p3_x + chord_offset_x + 5 * math.cos(angle_rad), 
               p3_y + chord_offset_y + 5 * math.sin(angle_rad))
        
        # Chord text
        chord_mid_x = (p2_x + p3_x) / 2 + chord_offset_x
        chord_mid_y = (p2_y + p3_y) / 2 + chord_offset_y
        c.saveState()
        c.translate(chord_mid_x, chord_mid_y)
        c.rotate(angle_deg / 2)
        c.drawString(-20, -10, f"{geometry['outer_chord_length']:.0f}")
        c.restoreState()
        
        # Inner chord
        inner_chord_offset_x = -(dim_offset + 20) * math.sin(angle_rad)
        inner_chord_offset_y = (dim_offset + 20) * math.cos(angle_rad)
        c.line(p1_x + inner_chord_offset_x - 5 * math.cos(angle_rad),
               p1_y + inner_chord_offset_y - 5 * math.sin(angle_rad),
               p4_x + inner_chord_offset_x + 5 * math.cos(angle_rad),
               p4_y + inner_chord_offset_y + 5 * math.sin(angle_rad))
        
        # Inner chord text
        inner_chord_mid_x = (p1_x + p4_x) / 2 + inner_chord_offset_x
        inner_chord_mid_y = (p1_y + p4_y) / 2 + inner_chord_offset_y
        c.saveState()
        c.translate(inner_chord_mid_x, inner_chord_mid_y)
        c.rotate(angle_deg / 2)
        c.drawString(-20, -10, f"{geometry['inner_chord_length']:.0f}")
        c.restoreState()
        
        # Arc dimensions (above and below the chords)
        # Outer arc
        outer_arc_r = outer_r + dim_offset + 35
        arc_path = c.beginPath()
        for i in range(21):
            angle = angle_rad * i / 20
            x = outer_arc_r * math.cos(angle)
            y = outer_arc_r * math.sin(angle)
            if i == 0:
                arc_path.moveTo(x, y)
            else:
                arc_path.lineTo(x, y)
        c.drawPath(arc_path)
        
        # Arc text
        arc_text_angle = angle_rad / 2
        arc_text_x = (outer_r + dim_offset + 40) * math.cos(arc_text_angle)
        arc_text_y = (outer_r + dim_offset + 40) * math.sin(arc_text_angle)
        c.drawString(arc_text_x - 20, arc_text_y - 3, f"{geometry['outer_arc_length']:.0f}")
        
        # Inner arc
        inner_arc_r = inner_r - dim_offset - 10
        if inner_arc_r > 0:  # Only draw if radius is positive
            arc_path = c.beginPath()
            for i in range(21):
                angle = angle_rad * i / 20
                x = inner_arc_r * math.cos(angle)
                y = inner_arc_r * math.sin(angle)
                if i == 0:
                    arc_path.moveTo(x, y)
                else:
                    arc_path.lineTo(x, y)
            c.drawPath(arc_path)
            
            # Inner arc text
            inner_arc_text_x = inner_arc_r * math.cos(arc_text_angle)
            inner_arc_text_y = inner_arc_r * math.sin(arc_text_angle)
            c.drawString(inner_arc_text_x - 20, inner_arc_text_y - 3, f"{geometry['inner_arc_length']:.0f}")
        
        # Radii labels with center indication
        c.setDash([2, 2])
        c.line(0, 0, p2_x + dim_offset + 30, 0)
        c.setDash([])
        
        c.drawString(p2_x + dim_offset + 35, 5, f"R{geometry['outer_radius']:.0f}")
        c.drawString(p2_x + dim_offset + 35, -15, f"R{geometry['inner_radius']:.0f}")
        
        # Angle at center
        c.setFont("Helvetica", 9)
        angle_label_r = inner_r * 0.3
        arc_path = c.beginPath()
        arc_path.arc(0, 0, angle_label_r, 0, angle_deg)
        c.drawPath(arc_path)
        angle_label_x = angle_label_r * math.cos(arc_text_angle)
        angle_label_y = angle_label_r * math.sin(arc_text_angle)
        c.drawString(angle_label_x - 10, angle_label_y - 3, f"{angle_deg:.0f}°")
        
        # Unit ID
        c.setFont("Helvetica-Bold", 10)
        c.setStrokeColor(black)
        c.drawString((p1_x + p3_x) / 2 - 10, -outer_r * 0.3, unit['id'])
        
        c.restoreState()


# Streamlit Application
def main():
    # Header
    st.markdown('<h1 class="main-header">📐 Ring Segment Generator</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Generate DXF files and technical drawings for curved stone units</p>', 
                unsafe_allow_html=True)
    
    # Sidebar for project information
    with st.sidebar:
        st.header("📋 Project Information")
        
        company = st.text_input("Company Name", value="London Stone")
        project = st.text_input("Project Name", placeholder="e.g., Museum Extension")
        customer = st.text_input("Customer Name", placeholder="e.g., Natural History Museum")
        order_number = st.text_input("Order Number", placeholder="e.g., LS-2024-001")
        
        st.divider()
        st.info("💡 **Tip**: Add multiple units with different specifications, "
                "then download all DXF files and a comprehensive PDF drawing.")
    
    # Main content area
    col1, col2 = st.columns([3, 2])
    
    with col1:
        st.header("Unit Specifications")
        
        # Input method selection
        input_method = st.radio(
            "Select dimension input method:",
            ["Radii + Chord Length", "Radii + Arc Length", "Radii + Angle", "Radius + Depth + Chord"]
        )
        
        # Dynamic input fields
        with st.form("unit_form"):
            unit_id = st.text_input("Unit ID/Type", placeholder="e.g., Type-A, Unit-1")
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                if "Depth" in input_method:
                    inner_radius = st.number_input("Inner Radius (mm)", min_value=0.0, value=1000.0)
                    depth = st.number_input("Depth (mm)", min_value=0.0, value=200.0)
                    outer_radius = None
                else:
                    inner_radius = st.number_input("Inner Radius (mm)", min_value=0.0, value=1000.0)
                    outer_radius = st.number_input("Outer Radius (mm)", min_value=0.0, value=1200.0)
                    depth = None
            
            with col_b:
                if "Chord" in input_method:
                    chord_length = st.number_input("Chord Length (mm)", min_value=0.0, value=500.0)
                    arc_length = None
                    angle_degrees = None
                elif "Arc" in input_method:
                    arc_length = st.number_input("Arc Length (mm)", min_value=0.0, value=600.0)
                    chord_length = None
                    angle_degrees = None
                else:  # Angle
                    angle_degrees = st.number_input("Angle (degrees)", min_value=0.0, max_value=360.0, value=30.0)
                    chord_length = None
                    arc_length = None
            
            submit_button = st.form_submit_button("➕ Add Unit", use_container_width=True, type="primary")
    
    # Initialize session state
    if 'units' not in st.session_state:
        st.session_state.units = []
    
    # Handle form submission
    if submit_button:
        if not unit_id:
            st.error("Please enter a Unit ID")
        else:
            try:
                # Calculate geometry
                geometry = RingSegmentGenerator.calculate_segment_geometry(
                    inner_radius=inner_radius,
                    outer_radius=outer_radius,
                    depth=depth,
                    chord_length=chord_length if "Chord" in input_method else None,
                    arc_length=arc_length if "Arc" in input_method else None,
                    angle_degrees=angle_degrees if "Angle" in input_method else None
                )
                
                # Add to session state
                st.session_state.units.append({
                    'id': unit_id,
                    'geometry': geometry
                })
                
                st.success(f"✅ Unit {unit_id} added successfully!")
                
            except ValueError as e:
                st.error(f"❌ Error: {str(e)}")
    
    # Display units
    with col2:
        st.header("Added Units")
        
        if st.session_state.units:
            for idx, unit in enumerate(st.session_state.units):
                with st.expander(f"📦 {unit['id']}", expanded=True):
                    g = unit['geometry']
                    st.write(f"**Inner Radius:** {g['inner_radius']:.0f} mm")
                    st.write(f"**Outer Radius:** {g['outer_radius']:.0f} mm")
                    st.write(f"**Angle:** {g['angle_degrees']:.1f}°")
                    st.write(f"**Chord Length:** {g['outer_chord_length']:.0f} mm")
                    st.write(f"**Arc Length:** {g['outer_arc_length']:.0f} mm")
                    
                    if st.button(f"🗑️ Remove", key=f"remove_{idx}"):
                        st.session_state.units.pop(idx)
                        st.rerun()
        else:
            st.info("No units added yet. Use the form to add units.")
        
        # Clear all button
        if st.session_state.units:
            if st.button("🗑️ Clear All Units", use_container_width=True):
                st.session_state.units = []
                st.rerun()
    
    # Download section
    if st.session_state.units:
        st.divider()
        st.header("📥 Download Files")
        
        col_download1, col_download2 = st.columns(2)
        
        with col_download1:
            # Generate ZIP with all DXF files
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for unit in st.session_state.units:
                    dxf_content = RingSegmentGenerator.create_dxf_segment(unit['geometry'])
                    zip_file.writestr(f"{unit['id']}.dxf", dxf_content)
            
            zip_buffer.seek(0)
            
            st.download_button(
                label="📦 Download All DXF Files (ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"ring_segments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip",
                use_container_width=True
            )
        
        with col_download2:
            # Generate PDF
            project_info = {
                'company': company or "London Stone",
                'project': project or "Ring Segments",
                'customer': customer or "Customer",
                'order_number': order_number or f"ORD-{datetime.now().strftime('%Y%m%d')}"
            }
            
            pdf_content = RingSegmentGenerator.create_pdf_drawing(
                st.session_state.units, project_info
            )
            
            if pdf_content:
                st.download_button(
                    label="📄 Download Technical Drawing (PDF)",
                    data=pdf_content,
                    file_name=f"technical_drawing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
    
    # Instructions
    with st.expander("📖 How to Use", expanded=False):
        st.markdown("""
        1. **Enter project information** in the sidebar
        2. **Choose your input method** based on available measurements
        3. **Add units** one by one with their specifications
        4. **Review** added units in the right panel
        5. **Download** individual DXF files (ZIP) and the technical PDF drawing
        
        **Notes:**
        - Chord length is the straight-line distance between arc endpoints
        - All DXF files use millimetres as units
        - The PDF includes all units with dimensions for client approval
        """)


if __name__ == "__main__":
    main()
