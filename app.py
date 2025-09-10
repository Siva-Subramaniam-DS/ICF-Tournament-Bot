"""
ICF Tournament Bot - Discord Bot for Tournament Management
Version: 3.0.0
Last Updated: September 7, 2025
Description: Comprehensive tournament management system for ICF competitions
Features: Match scheduling, judge assignment, rule management, result tracking
"""

import discord
from discord import app_commands
from discord.ext import commands
import os
import random
from dotenv import load_dotenv
from itertools import combinations
from typing import Optional
import re
import datetime
import asyncio
import glob
from discord.ui import Button, View
import pytz
from PIL import Image, ImageDraw, ImageFont
# Removed pilmoji import due to dependency issues
import io
import json

# Load environment variables
load_dotenv()

# Channel IDs for event management
CHANNEL_IDS = {
    "schedules": 1413926551044751542,
    "match_results": 1413924771699097721,
    "match_reports": 1414247921896919182
}

# Role IDs for permissions
ROLE_IDS = {
    "helpers_tournament": 1385296509289107671,
    "organizers": 1385296705179619450
}

# Set Windows event loop policy for asyncio
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Store scheduled events for reminders
scheduled_events = {}

# Load scheduled events from file on startup
def load_scheduled_events():
    global scheduled_events
    try:
        if os.path.exists('scheduled_events.json'):
            with open('scheduled_events.json', 'r') as f:
                data = json.load(f)
                # Convert datetime strings back to datetime objects
                for event_id, event_data in data.items():
                    if 'datetime' in event_data:
                        event_data['datetime'] = datetime.datetime.fromisoformat(event_data['datetime'])
                scheduled_events = data
                print(f"Loaded {len(scheduled_events)} scheduled events from file")
    except Exception as e:
        print(f"Error loading scheduled events: {e}")
        scheduled_events = {}

# Save scheduled events to file
def save_scheduled_events():
    try:
        # Convert datetime objects to strings for JSON serialization
        data_to_save = {}
        for event_id, event_data in scheduled_events.items():
            event_copy = event_data.copy()
            if 'datetime' in event_copy:
                event_copy['datetime'] = event_copy['datetime'].isoformat()
            # Remove non-serializable objects like discord.Member
            if 'judge' in event_copy:
                event_copy['judge'] = None
            data_to_save[event_id] = event_copy
        
        with open('scheduled_events.json', 'w') as f:
            json.dump(data_to_save, f, indent=2)
    except Exception as e:
        print(f"Error saving scheduled events: {e}")

# Track per-event reminder tasks (for cancellation/update)
reminder_tasks = {}

# Store judge assignments to prevent overloading
judge_assignments = {}  # {judge_id: [event_ids]}

# ===========================================================================================
# RULE MANAGEMENT SYSTEM
# ===========================================================================================

# Store tournament rules in memory
tournament_rules = {}

def load_rules():
    """Load rules from persistent storage"""
    global tournament_rules
    try:
        if os.path.exists('tournament_rules.json'):
            with open('tournament_rules.json', 'r', encoding='utf-8') as f:
                tournament_rules = json.load(f)
                print(f"Loaded tournament rules from file")
        else:
            tournament_rules = {}
            print("No existing rules file found, starting with empty rules")
    except Exception as e:
        print(f"Error loading tournament rules: {e}")
        tournament_rules = {}

def save_rules():
    """Save rules to persistent storage"""
    try:
        with open('tournament_rules.json', 'w', encoding='utf-8') as f:
            json.dump(tournament_rules, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving tournament rules: {e}")
        return False

def get_current_rules():
    """Get current rules content"""
    return tournament_rules.get('rules', {}).get('content', '')

def set_rules_content(content, user_id, username):
    """Set new rules content with metadata"""
    global tournament_rules
    
    # Sanitize content (basic cleanup)
    if content:
        content = content.strip()
    
    # Update rules with metadata
    tournament_rules['rules'] = {
        'content': content,
        'last_updated': datetime.datetime.utcnow().isoformat(),
        'updated_by': {
            'user_id': user_id,
            'username': username
        },
        'version': tournament_rules.get('rules', {}).get('version', 0) + 1
    }
    
    return save_rules()

def has_organizer_permission(interaction):
    """Check if user has organizer permissions for rule management"""
    organizers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["organizers"])
    return organizers_role is not None

# Embed field utility functions for safe Discord.py embed manipulation
def find_field_index(embed: discord.Embed, field_name: str) -> int:
    """Find the index of a field by name. Returns -1 if not found."""
    try:
        for i, field in enumerate(embed.fields):
            if field.name == field_name:
                return i
        return -1
    except Exception as e:
        print(f"Error finding field index: {e}")
        return -1

def remove_field_by_name(embed: discord.Embed, field_name: str) -> bool:
    """Safely remove a field by name using Discord.py methods. Returns True if removed, False if not found."""
    try:
        field_index = find_field_index(embed, field_name)
        if field_index != -1:
            embed.remove_field(field_index)
            return True
        return False
    except Exception as e:
        print(f"Error removing field by name '{field_name}': {e}")
        return False

def update_judge_field(embed: discord.Embed, judge_member: discord.Member) -> bool:
    """Update or add judge field safely. Returns True if successful."""
    try:
        # Remove existing judge field if it exists
        remove_field_by_name(embed, "👨‍⚖️ Judge")
        
        # Add new judge field
        embed.add_field(
            name="👨‍⚖️ Judge", 
            value=f"{judge_member.mention} `@{judge_member.name}`", 
            inline=True
        )
        return True
    except Exception as e:
        print(f"Error updating judge field: {e}")
        return False

def remove_judge_field(embed: discord.Embed) -> bool:
    """Remove judge field safely. Returns True if removed, False if not found."""
    try:
        return remove_field_by_name(embed, "👨‍⚖️ Judge")
    except Exception as e:
        print(f"Error removing judge field: {e}")
        return False

def can_judge_take_schedule(judge_id: int, max_assignments: int = 3) -> tuple[bool, str]:
    """Check if a judge can take another schedule"""
    if judge_id not in judge_assignments:
        return True, ""
    
    current_assignments = len(judge_assignments[judge_id])
    if current_assignments >= max_assignments:
        return False, f"You already have {current_assignments} schedule(s) assigned. Maximum allowed is {max_assignments}."
    
    return True, ""

def add_judge_assignment(judge_id: int, event_id: str):
    """Add a schedule assignment to a judge"""
    if judge_id not in judge_assignments:
        judge_assignments[judge_id] = []
    judge_assignments[judge_id].append(event_id)

def remove_judge_assignment(judge_id: int, event_id: str):
    """Remove a schedule assignment from a judge"""
    if judge_id in judge_assignments and event_id in judge_assignments[judge_id]:
        judge_assignments[judge_id].remove(event_id)
        if not judge_assignments[judge_id]:  # Remove empty list
            del judge_assignments[judge_id]

class TakeScheduleButton(View):
    def __init__(self, event_id: str, team1_captain: discord.Member, team2_captain: discord.Member, event_channel: discord.TextChannel = None):
        super().__init__(timeout=None)
        self.event_id = event_id
        self.team1_captain = team1_captain
        self.team2_captain = team2_captain
        self.event_channel = event_channel
        self.judge = None
        self._taking_schedule = False  # Flag to prevent race conditions
        
    @discord.ui.button(label="Take Schedule", style=discord.ButtonStyle.green, emoji="📋")
    async def take_schedule(self, interaction: discord.Interaction, button: Button):
        # Prevent race conditions by checking if someone is already taking the schedule
        if self._taking_schedule:
            await interaction.response.send_message("⏳ Another judge is currently taking this schedule. Please wait a moment.", ephemeral=True)
            return
            
        # Check if user has Helpers Tournament or Organizers role
        organizers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["organizers"])
        helpers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["helpers_tournament"])
        if not (organizers_role or helpers_role):
            await interaction.response.send_message("❌ You need **Organizers** or **Helpers Tournament** role to take this schedule.", ephemeral=True)
            return
            
        # Check if already taken
        if self.judge:
            await interaction.response.send_message(f"❌ This schedule has already been taken by {self.judge.display_name}.", ephemeral=True)
            return
        
        # Check if judge can take more schedules
        can_take, error_message = can_judge_take_schedule(interaction.user.id, max_assignments=3)
        if not can_take:
            await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)
            return
        
        # Set flag to prevent race conditions
        self._taking_schedule = True
        
        try:
            # Defer response to give us time to process
            await interaction.response.defer(ephemeral=True)
            
            # Double-check if still available (in case another judge took it while we were processing)
            if self.judge:
                await interaction.followup.send(f"❌ This schedule has already been taken by {self.judge.display_name}.", ephemeral=True)
                return
            
            # Assign judge
            self.judge = interaction.user
            
            # Add to judge assignments tracking
            add_judge_assignment(interaction.user.id, self.event_id)
            
            # Update button appearance
            button.label = f"Taken by {interaction.user.display_name}"
            button.style = discord.ButtonStyle.gray
            button.disabled = True
            button.emoji = "✅"
            
            # Update the embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green()
            
            # Update judge field using safe utility function
            if not update_judge_field(embed, interaction.user):
                await interaction.followup.send("❌ Failed to update embed with judge information.", ephemeral=True)
                return
            
            # Update the message
            await interaction.message.edit(embed=embed, view=self)
            
            # Send success message
            await interaction.followup.send("✅ You have successfully taken this schedule!", ephemeral=True)
            
            # Send notification to the event channel
            await self.send_judge_assignment_notification(interaction.user)
            
            # Update scheduled events with judge
            if self.event_id in scheduled_events:
                scheduled_events[self.event_id]['judge'] = self.judge
            
        except Exception as e:
            # Reset flag in case of error
            self._taking_schedule = False
            print(f"Error in take_schedule: {e}")
            await interaction.followup.send(f"❌ An error occurred while taking the schedule: {str(e)}", ephemeral=True)
        finally:
            # Reset flag after processing
            self._taking_schedule = False


    
    
    
    async def send_judge_assignment_notification(self, judge: discord.Member):
        """Send notification to the event channel when a judge is assigned and add judge to channel"""
        if not self.event_channel:
            return
        
        try:
            # Add judge to the event channel with proper permissions
            await self.event_channel.set_permissions(
                judge, 
                read_messages=True, 
                send_messages=True, 
                view_channel=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True
            )
            
            # Create notification embed
            embed = discord.Embed(
                title="👨‍⚖️ Judge Assigned",
                description=f"**{judge.display_name}** has been assigned as the judge for this match!",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="📋 Match Details",
                value=f"**Team 1:** {self.team1_captain.mention}\n**Team 2:** {self.team2_captain.mention}",
                inline=False
            )
            
            embed.add_field(
                name="👨‍⚖️ Judge",
                value=f"{judge.mention} `@{judge.name}`\n✅ **Added to channel**",
                inline=True
            )
            
            embed.set_footer(text="Judge Assignment • ICF Tournament Bot")
            
            # Send notification to the event channel
            await self.event_channel.send(
                content=f"🔔 {judge.mention} {self.team1_captain.mention} {self.team2_captain.mention}",
                embed=embed
            )
            
        except discord.Forbidden:
            print(f"Error: Bot doesn't have permission to add {judge.display_name} to channel {self.event_channel.name}")
        except Exception as e:
            print(f"Error sending judge assignment notification: {e}")
    


# ===========================================================================================
# RULE MANAGEMENT UI COMPONENTS
# ===========================================================================================

class RuleInputModal(discord.ui.Modal):
    """Modal for entering/editing rule content"""
    
    def __init__(self, title: str, current_content: str = ""):
        super().__init__(title=title)
        
        # Text input field for rule content
        self.rule_input = discord.ui.TextInput(
            label="Tournament Rules",
            placeholder="Enter the tournament rules here...",
            default=current_content,
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=False
        )
        self.add_item(self.rule_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Get the content from the input
            content = self.rule_input.value.strip()
            
            # Save the rules
            success = set_rules_content(content, interaction.user.id, interaction.user.name)
            
            if success:
                # Create confirmation embed
                embed = discord.Embed(
                    title="✅ Rules Updated Successfully",
                    description="Tournament rules have been saved.",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                
                if content:
                    # Show preview of rules (truncated if too long)
                    preview = content[:500] + "..." if len(content) > 500 else content
                    embed.add_field(name="Rules Preview", value=f"```\n{preview}\n```", inline=False)
                else:
                    embed.add_field(name="Status", value="Rules have been cleared (empty)", inline=False)
                
                embed.set_footer(text=f"Updated by {interaction.user.name}")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to save rules. Please try again.", ephemeral=True)
                
        except Exception as e:
            print(f"Error in rule modal submission: {e}")
            await interaction.response.send_message("❌ An error occurred while saving rules.", ephemeral=True)

class RulesManagementView(discord.ui.View):
    """Interactive view for organizers with rule management buttons"""
    
    def __init__(self):
        super().__init__(timeout=300)  # 5 minute timeout
    
    @discord.ui.button(label="Enter Rules", style=discord.ButtonStyle.green, emoji="📝")
    async def enter_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to enter new rules"""
        modal = RuleInputModal("Enter Tournament Rules")
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Reedit Rules", style=discord.ButtonStyle.primary, emoji="✏️")
    async def reedit_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to edit existing rules"""
        current_rules = get_current_rules()
        
        if not current_rules:
            await interaction.response.send_message("❌ No rules are currently set. Use 'Enter Rules' to create new rules.", ephemeral=True)
            return
        
        modal = RuleInputModal("Edit Tournament Rules", current_rules)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Show Rules", style=discord.ButtonStyle.secondary, emoji="👁️")
    async def show_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to display current rules"""
        await display_rules(interaction)

async def display_rules(interaction: discord.Interaction):
    """Display current tournament rules in an embed"""
    try:
        global tournament_rules
        current_rules = get_current_rules()
        
        if not current_rules:
            embed = discord.Embed(
                title="📋 Tournament Rules",
                description="No tournament rules have been set yet.",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text="ICF Tournament System")
        else:
            embed = discord.Embed(
                title="📋 Tournament Rules",
                description=current_rules,
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            # Add metadata if available
            if 'rules' in tournament_rules and 'last_updated' in tournament_rules['rules']:
                updated_by = tournament_rules['rules'].get('updated_by', {}).get('username', 'Unknown')
                embed.set_footer(text=f"ICF Tournament Bot • Last updated by {updated_by}")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)
        
    except Exception as e:
        print(f"Error displaying rules: {e}")
        await interaction.response.send_message("❌ An error occurred while displaying rules.", ephemeral=False)

# ===========================================================================================
# NOTIFICATION AND REMINDER SYSTEM (Ten-minute reminder for captains and judge)
# ===========================================================================================

async def send_ten_minute_reminder(event_id: str, team1_captain: discord.Member, team2_captain: discord.Member, judge: Optional[discord.Member], event_channel: discord.TextChannel, match_time: datetime.datetime):
    """Send 10-minute reminder notification to judge and captains"""
    try:
        if not event_channel:
            print(f"No event channel provided for event {event_id}")
            return

        # Get the latest judge from scheduled_events if available
        resolved_judge = judge
        if event_id in scheduled_events:
            stored_judge = scheduled_events[event_id].get('judge')
            if stored_judge:
                resolved_judge = stored_judge

        # Create reminder embed
        embed = discord.Embed(
            title="⏰ 10-MINUTE MATCH REMINDER",
            description=f"**Your tournament match is starting in 10 minutes!**",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="🕒 Match Time", value=f"<t:{int(match_time.timestamp())}:F>", inline=False)
        embed.add_field(name="👥 Team Captains", value=f"{team1_captain.mention} vs {team2_captain.mention}", inline=False)
        if resolved_judge:
            embed.add_field(name="👨‍⚖️ Judge", value=f"{resolved_judge.mention}", inline=False)
        embed.add_field(name="� ActAion Required", value="Please prepare for the match and join the designated channel.", inline=False)
        embed.set_footer(text="Tournament Management System")

        # Send notification with pings
        pings = f"{team1_captain.mention} {team2_captain.mention}"
        if resolved_judge:
            pings = f"{resolved_judge.mention} " + pings
        notification_text = f"🔔 **MATCH REMINDER**\n\n{pings}\n\nYour match starts in **10 minutes**!"

        await event_channel.send(content=notification_text, embed=embed)
        print(f"10-minute reminder sent for event {event_id}")
    except Exception as e:
        print(f"Error sending 10-minute reminder for event {event_id}: {e}")


async def schedule_ten_minute_reminder(event_id: str, team1_captain: discord.Member, team2_captain: discord.Member, judge: Optional[discord.Member], event_channel: discord.TextChannel, match_time: datetime.datetime):
    """Schedule a 10-minute reminder for the match"""
    try:
        # Calculate when to send the 10-minute reminder
        reminder_time = match_time - datetime.timedelta(minutes=10)
        now = datetime.datetime.now(pytz.UTC)

        # Ensure match_time and reminder_time are timezone-aware UTC
        if match_time.tzinfo is None:
            match_time = match_time.replace(tzinfo=pytz.UTC)
            reminder_time = match_time - datetime.timedelta(minutes=10)

        # Check if reminder time is in the future
        if reminder_time <= now:
            print(f"Reminder time for event {event_id} is in the past, skipping")
            return

        # Calculate delay in seconds
        delay_seconds = (reminder_time - now).total_seconds()

        async def reminder_task():
            try:
                await asyncio.sleep(delay_seconds)
                await send_ten_minute_reminder(event_id, team1_captain, team2_captain, judge, event_channel, match_time)
            except asyncio.CancelledError:
                print(f"Reminder task for event {event_id} was cancelled")
            except Exception as e:
                print(f"Error in reminder task for event {event_id}: {e}")

        # Cancel existing reminder if any
        if event_id in reminder_tasks:
            reminder_tasks[event_id].cancel()

        # Schedule new reminder
        reminder_tasks[event_id] = asyncio.create_task(reminder_task())
        print(f"10-minute reminder scheduled for event {event_id} at {reminder_time}")
    except Exception as e:
        print(f"Error scheduling 10-minute reminder for event {event_id}: {e}")


async def schedule_event_reminder_v2(event_id: str, team1_captain: discord.Member, team2_captain: discord.Member, judge: Optional[discord.Member], event_channel: discord.TextChannel):
    """Schedule event reminder with 10-minute notification using stored event datetime"""
    try:
        if event_id not in scheduled_events:
            print(f"Event {event_id} not found in scheduled_events")
            return
        event_data = scheduled_events[event_id]
        match_time = event_data.get('datetime')
        if not match_time:
            print(f"No datetime found for event {event_id}")
            return
        # Ensure timezone-aware UTC
        if match_time.tzinfo is None:
            match_time = match_time.replace(tzinfo=pytz.UTC)
        await schedule_ten_minute_reminder(event_id, team1_captain, team2_captain, judge, event_channel, match_time)
    except Exception as e:
        print(f"Error in schedule_event_reminder_v2 for event {event_id}: {e}")

def get_random_template():
    """Get a random template image from the Templates folder"""
    template_path = "Templates"
    if os.path.exists(template_path):
        # Get all image files
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif']
        image_files = []
        for ext in image_extensions:
            image_files.extend(glob.glob(os.path.join(template_path, ext)))
            image_files.extend(glob.glob(os.path.join(template_path, ext.upper())))
        
        if image_files:
            return random.choice(image_files)
    return None

def create_event_poster(template_path: str, round_num: int, team1_captain: str, team2_captain: str, utc_time: str, date_str: str = None, tournament_name: str = "ICF Tournament", server_name: str = "ICF Tournament Bot") -> str:
    """Create event poster with text overlays"""
    try:
        # Open the template image
        with Image.open(template_path) as img:
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Resize image to be smaller (max 800x600 to avoid Discord size limits)
            max_width, max_height = 800, 600
            width, height = img.size
            
            # Calculate new dimensions while maintaining aspect ratio
            if width > max_width or height > max_height:
                ratio = min(max_width / width, max_height / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create a copy to work with
            poster = img.copy()
            draw = ImageDraw.Draw(poster)
            
            # Use regular PIL drawing (emojis will be displayed as text)
            
            # Get image dimensions
            width, height = poster.size
            
            # Try to load fonts with better visibility and readability
            try:
                # Try multiple font options for better visibility
                font_options = [
                    "C:/Windows/Fonts/segoeuib.ttf",    # Segoe UI Bold (good Unicode coverage)
                    "C:/Windows/Fonts/arialuni.ttf",    # Arial Unicode MS (broad glyph support, if installed)
                    "C:/Windows/Fonts/segoeui.ttf",     # Segoe UI Regular
                    "C:/Windows/Fonts/verdanab.ttf",    # Verdana Bold
                    "C:/Windows/Fonts/trebucbd.ttf",    # Trebuchet MS Bold
                    "C:/Windows/Fonts/arialbd.ttf",     # Arial Bold
                    "C:/Windows/Fonts/calibrib.ttf",    # Calibri Bold
                    "C:/Windows/Fonts/impact.ttf",      # Impact
                ]
                
                font_path = None
                for font_option in font_options:
                    if os.path.exists(font_option):
                        font_path = font_option
                        break
                
                if font_path:
                    # Use larger, more visible font sizes
                    # Slightly reduce sizes for faster layout and better fit
                    font_title = ImageFont.truetype(font_path, int(height * 0.13))
                    font_large = ImageFont.truetype(font_path, int(height * 0.17))
                    font_medium = ImageFont.truetype(font_path, int(height * 0.11))
                    font_small = ImageFont.truetype(font_path, int(height * 0.085))
                    font_tiny = ImageFont.truetype(font_path, int(height * 0.065))
                else:
                    raise Exception("No suitable font found")
                    
            except:
                try:
                    # Fallback to regular Arial with bigger sizes
                    font_title = ImageFont.truetype("arial.ttf", int(height * 0.14))
                    font_large = ImageFont.truetype("arial.ttf", int(height * 0.18))
                    font_medium = ImageFont.truetype("arial.ttf", int(height * 0.12))
                    font_small = ImageFont.truetype("arial.ttf", int(height * 0.09))
                    font_tiny = ImageFont.truetype("arial.ttf", int(height * 0.07))
                except:
                    # Final fallback to default font with larger sizes
                    try:
                        font_title = ImageFont.load_default().font_variant(size=int(height * 0.14))
                        font_large = ImageFont.load_default().font_variant(size=int(height * 0.18))
                        font_medium = ImageFont.load_default().font_variant(size=int(height * 0.12))
                        font_small = ImageFont.load_default().font_variant(size=int(height * 0.09))
                        font_tiny = ImageFont.load_default().font_variant(size=int(height * 0.07))
                    except:
                        font_title = ImageFont.load_default()
                        font_large = ImageFont.load_default()
                        font_medium = ImageFont.load_default()
                        font_small = ImageFont.load_default()
                        font_tiny = ImageFont.load_default()
            
            # Define colors for clean visibility without backgrounds
            text_color = (255, 255, 255)  # Bright white
            outline_color = (0, 0, 0)     # Pure black
            yellow_color = (255, 255, 0)  # Bright yellow for important text
            
            # Simple helper function with outline only (no background)
            def draw_text_with_outline(text, x, y, font, text_color=text_color, use_yellow=False):
                # Convert coordinates to integers
                x, y = int(x), int(y)
                
                # Choose text color
                final_text_color = yellow_color if use_yellow else text_color
                
                # Draw thick black outline for visibility
                outline_width = 4
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
                
                # Draw main text on top
                draw.text((x, y), text, font=font, fill=final_text_color)
            
            def draw_emoji_text_with_outline(text, x, y, font, text_color=text_color):
                # Convert coordinates to integers
                x, y = int(x), int(y)
                
                # Draw thick black outline
                outline_width = 3
                for dx in range(-outline_width, outline_width + 1):
                    for dy in range(-outline_width, outline_width + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
                
                # Draw main text on top
                draw.text((x, y), text, font=font, fill=text_color)
            
            # Add ICF logo if available
            try:
                logo_path = "Logo_ICF_2025_400.png"
                if os.path.exists(logo_path):
                    with Image.open(logo_path) as logo_img:
                        # Resize logo to fit nicely (max 15% of poster height)
                        logo_max_height = int(height * 0.15)
                        logo_width, logo_height = logo_img.size
                        if logo_height > logo_max_height:
                            ratio = logo_max_height / logo_height
                            new_logo_width = int(logo_width * ratio)
                            logo_img = logo_img.resize((new_logo_width, logo_max_height), Image.Resampling.LANCZOS)
                        
                        # Position logo at top center
                        logo_x = (width - logo_img.width) // 2
                        logo_y = int(height * 0.05)
                        
                        # Paste logo onto poster
                        if logo_img.mode == 'RGBA':
                            poster.paste(logo_img, (logo_x, logo_y), logo_img)
                        else:
                            poster.paste(logo_img, (logo_x, logo_y))
            except Exception as e:
                print(f"Error adding logo: {e}")
            
            # Add server name text (below logo, center, bold)
            server_text = server_name
            server_bbox = draw.textbbox((0, 0), server_text, font=font_title)
            server_width = server_bbox[2] - server_bbox[0]
            server_x = (width - server_width) // 2
            server_y = int(height * 0.22)  # Moved down to accommodate logo
            draw_text_with_outline(server_text, server_x, server_y, font_title)
            
            # Add Round text (center) - use yellow for emphasis with more spacing
            round_text = f"ROUND {round_num}"
            round_bbox = draw.textbbox((0, 0), round_text, font=font_large)
            round_width = round_bbox[2] - round_bbox[0]
            round_x = (width - round_width) // 2
            round_y = int(height * 0.40)  # Adjusted for logo space
            draw_text_with_outline(round_text, round_x, round_y, font_large, use_yellow=True)
            
            # Add Captain vs Captain text (center) with more spacing
            vs_text = f"{team1_captain} VS {team2_captain}"
            vs_bbox = draw.textbbox((0, 0), vs_text, font=font_medium)
            vs_width = vs_bbox[2] - vs_bbox[0]
            vs_x = (width - vs_width) // 2
            vs_y = int(height * 0.58)  # Adjusted for logo space
            draw_text_with_outline(vs_text, vs_x, vs_y, font_medium)
            
            # Add date (if provided) with more spacing
            if date_str:
                date_text = f"📅 {date_str}"
                date_bbox = draw.textbbox((0, 0), date_text, font=font_small)
                date_width = date_bbox[2] - date_bbox[0]
                date_x = (width - date_width) // 2
                date_y = int(height * 0.72)  # More space between captains and date
                draw_emoji_text_with_outline(date_text, date_x, date_y, font_small)
            
            # Add UTC time with more spacing
            time_text = f"🕐 {utc_time}"
            time_bbox = draw.textbbox((0, 0), time_text, font=font_small)
            time_width = time_bbox[2] - time_bbox[0]
            time_x = (width - time_width) // 2
            time_y = int(height * 0.82) if date_str else int(height * 0.75)  # More space between date and time
            draw_emoji_text_with_outline(time_text, time_x, time_y, font_small)
            
            # "MATCH SCHEDULED" text removed as requested
            
            # Save the modified image (no overlay compositing needed)
            output_path = f"temp_poster_{int(datetime.datetime.now().timestamp())}.png"
            poster.save(output_path, "PNG")
            return output_path
            
    except Exception as e:
        print(f"Error creating poster: {e}")
        return None

def calculate_time_difference(event_datetime: datetime.datetime, user_timezone: str = None) -> dict:
    """Calculate time difference and format for different timezones"""
    current_time = datetime.datetime.now()
    time_diff = event_datetime - current_time
    minutes_remaining = int(time_diff.total_seconds() / 60)
    
    # Format UTC time exactly as requested
    utc_time_str = event_datetime.strftime("%H:%M utc, %d/%m")
    
    # Try to detect user's local timezone
    local_timezone = None
    if user_timezone:
        try:
            local_timezone = pytz.timezone(user_timezone)
        except:
            pass
    
    # If no user timezone provided, try to detect from system
    if not local_timezone:
        try:
            # Try to get system timezone
            import time
            local_timezone = pytz.timezone(time.tzname[time.daylight])
        except:
            # Fallback to IST if detection fails
            local_timezone = pytz.timezone('Asia/Kolkata')
    
    # Calculate user's local time
    local_time = event_datetime.replace(tzinfo=pytz.UTC).astimezone(local_timezone)
    local_time_formatted = local_time.strftime("%A, %d %B, %Y %H:%M")
    
    # Calculate other common timezones
    ist_tz = pytz.timezone('Asia/Kolkata')
    ist_time = event_datetime.replace(tzinfo=pytz.UTC).astimezone(ist_tz)
    ist_formatted = ist_time.strftime("%A, %d %B, %Y %H:%M")
    
    est_tz = pytz.timezone('America/New_York')
    est_time = event_datetime.replace(tzinfo=pytz.UTC).astimezone(est_tz)
    est_formatted = est_time.strftime("%A, %d %B, %Y %H:%M")
    
    gmt_tz = pytz.timezone('Europe/London')
    gmt_time = event_datetime.replace(tzinfo=pytz.UTC).astimezone(gmt_tz)
    gmt_formatted = gmt_time.strftime("%A, %d %B, %Y %H:%M")
    
    return {
        'minutes_remaining': minutes_remaining,
        'utc_time': utc_time_str,
        'utc_time_simple': event_datetime.strftime("%H:%M UTC"),
        'local_time': local_time_formatted,
        'ist_time': ist_formatted,
        'est_time': est_formatted,
        'gmt_time': gmt_formatted
    }

def has_event_create_permission(interaction):
    """Check if user has permission to create events (Organizers or Helpers Tournament)"""
    organizers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["organizers"])
    helpers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["helpers_tournament"])
    return organizers_role is not None or helpers_role is not None

def has_event_result_permission(interaction):
    """Check if user has permission to post event results (Organizers or Helpers Tournament)"""
    organizers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["organizers"])
    helpers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["helpers_tournament"])
    return organizers_role is not None or helpers_role is not None

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    print(f"🆔 Bot ID: {bot.user.id}")
    print(f"📊 Connected to {len(bot.guilds)} guild(s)")
    
    # Load scheduled events from file
    load_scheduled_events()
    
    # Load tournament rules from file
    load_rules()
    
    # Sync commands with timeout handling
    try:
        print("🔄 Syncing slash commands...")
        import asyncio
        synced = await asyncio.wait_for(tree.sync(), timeout=30.0)
        print(f"✅ Synced {len(synced)} command(s)")
    except asyncio.TimeoutError:
        print("⚠️ Command sync timed out, but bot will continue running")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
        print("⚠️ Bot will continue running without command sync")
    
    print("🎯 Bot is ready to receive commands!")

@tree.command(name="help", description="Show all available Event Management slash commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎯 Event Management Bot - Command Guide",
        description="Complete list of available slash commands for event management.",
        color=discord.Color.blue()
    )

    # System Commands
    embed.add_field(
        name="⚙️ **System Commands**",
        value=(
            "`/help` - Display this command guide\n"
            "`/rules` - Manage or view tournament rules"
        ),
        inline=False
    )

    # Event Management
    embed.add_field(
        name="🏆 **Event Management**",
        value=(
            "`/event-create` - Create tournament events (Organizers/Helpers Tournament)\n"
            "`/event-result` - Record event results (Organizers/Helpers Tournament)\n"
            "`/event-delete` - Delete scheduled events (Organizers/Helpers Tournament)"
        ),
        inline=False
    )

    # Utility Commands
    embed.add_field(
        name="⚖️ **Utility Commands**",
        value=(
            "`/team_balance` - Balance teams by player levels\n"
            "`/time` - Generate random match time (12:00-17:59 UTC)\n"
            "`/choose` - Random choice from comma-separated options\n"
            "`/general_tie_breaker` - Break a tie using highest total score"
        ),
        inline=False
    )

    embed.set_footer(text="🎯 Event Management System • Powered by Discord.py")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="rules", description="Manage or view tournament rules")
async def rules_command(interaction: discord.Interaction):
    """Main rules command with role-based functionality"""
    try:
        # Check if user has organizer permissions
        if has_organizer_permission(interaction):
            # Organizer gets management interface
            embed = discord.Embed(
                title="📋 Tournament Rules Management",
                description="Choose an action to manage tournament rules:",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            
            current_rules = get_current_rules()
            if current_rules:
                embed.add_field(
                    name="Current Status", 
                    value="✅ Rules are set", 
                    inline=True
                )
                # Show preview of current rules
                preview = current_rules[:200] + "..." if len(current_rules) > 200 else current_rules
                embed.add_field(
                    name="Preview", 
                    value=f"```\n{preview}\n```", 
                    inline=False
                )
            else:
                embed.add_field(
                    name="Current Status", 
                    value="❌ No rules set", 
                    inline=True
                )
            
            embed.set_footer(text="ICF Tournament Bot • Organizer Panel")
            
            # Send with management buttons
            view = RulesManagementView()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            # Non-organizer gets direct rule display
            await display_rules(interaction)
            
    except Exception as e:
        print(f"Error in rules command: {e}")
        await interaction.response.send_message("❌ An error occurred while processing the rules command.", ephemeral=True)
    
@tree.command(name="team_balance", description="Balance two teams based on player levels")
@app_commands.describe(levels="Comma-separated player levels (e.g. 48,50,51,35,51,50,50,37,51,52)")
async def team_balance(interaction: discord.Interaction, levels: str):
    try:
        level_list = [int(x.strip()) for x in levels.split(",") if x.strip()]
        n = len(level_list)
        if n % 2 != 0:
            await interaction.response.send_message("❌ Number of players must be even (e.g., 8 or 10).", ephemeral=True)
            return

        team_size = n // 2
        min_diff = float('inf')
        best_team_a = []
        for combo in combinations(level_list, team_size):
            team_a = list(combo)
            team_b = list(level_list)
            for lvl in team_a:
                team_b.remove(lvl)
            diff = abs(sum(team_a) - sum(team_b))
            if diff < min_diff:
                min_diff = diff
                best_team_a = team_a
        team_b = list(level_list)
        for lvl in best_team_a:
            team_b.remove(lvl)
        sum_a = sum(best_team_a)
        sum_b = sum(team_b)
        diff = abs(sum_a - sum_b)
        await interaction.response.send_message(
            f"**Team A:** {best_team_a} | Total Level: {sum_a}\n"
            f"**Team B:** {team_b} | Total Level: {sum_b}\n"
            f"**Level Difference:** {diff}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@tree.command(name="event", description="Event management commands")
@app_commands.describe(
    action="Select the event action to perform"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="create", value="create"),
        app_commands.Choice(name="result", value="result")
    ]
)
async def event(interaction: discord.Interaction, action: app_commands.Choice[str]):
    """Base event command - this will be handled by subcommands"""
    await interaction.response.send_message(f"Please use `/event {action.value}` with the appropriate parameters.", ephemeral=True)

@tree.command(name="event-create", description="Creates an event (Organizers/Helpers Tournament)")
@app_commands.describe(
    team_1_captain="Captain of team 1",
    team_2_captain="Captain of team 2", 
    hour="Hour of the event (0-23)",
    minute="Minute of the event (0-59)",
    date="Date of the event",
    month="Month of the event",
    round="Round number",
    tournament="Tournament name (e.g. King of the Seas, Summer Cup, etc.)"
)
async def event_create(
    interaction: discord.Interaction,
    team_1_captain: discord.Member,
    team_2_captain: discord.Member,
    hour: int,
    minute: int,
    date: int,
    month: int,
    round: int,
    tournament: str
):
    """Creates an event with the specified parameters"""
    
    # Defer the response to give us more time for image processing
    await interaction.response.defer(ephemeral=True)
    
    # Check permissions
    if not has_event_create_permission(interaction):
        await interaction.followup.send("❌ You need **Organizers** or **Helpers Tournament** role to create events.", ephemeral=True)
        return
    
    # Validate input parameters
    if not (0 <= hour <= 23):
        await interaction.followup.send("❌ Hour must be between 0 and 23", ephemeral=True)
        return
    
    if not (1 <= date <= 31):
        await interaction.followup.send("❌ Date must be between 1 and 31", ephemeral=True)
        return

    if not (1 <= month <= 12):
        await interaction.followup.send("❌ Month must be between 1 and 12", ephemeral=True)
        return
            
    if not (0 <= minute <= 59):
        await interaction.followup.send("❌ Minute must be between 0 and 59", ephemeral=True)
        return

    # Generate unique event ID
    event_id = f"event_{int(datetime.datetime.now().timestamp())}"
    
    # Create event datetime
    current_year = datetime.datetime.now().year
    event_datetime = datetime.datetime(current_year, month, date, hour, minute)
    
    # Calculate time differences and format times
    time_info = calculate_time_difference(event_datetime)
    
    # Store event data for reminders
    scheduled_events[event_id] = {
        'title': f"Round {round} Match",
        'datetime': event_datetime,
        'time_str': time_info['utc_time'],
        'date_str': f"{date:02d}/{month:02d}",
        'round': f"Round {round}",
        'minutes_left': time_info['minutes_remaining'],
        'tournament': tournament,
        'judge': None,
        'channel_id': interaction.channel.id,
        'team1_captain': team_1_captain,
        'team2_captain': team_2_captain
    }
    
    # Save events to file
    save_scheduled_events()
    
    # Get random template image and create poster
    template_image = get_random_template()
    poster_image = None
    
    if template_image:
        try:
            # Create poster with text overlays
            poster_image = create_event_poster(
                template_image, 
                round, 
                team_1_captain.display_name, 
                team_2_captain.display_name, 
                time_info['utc_time_simple'],
                f"{date:02d}/{month:02d}/{current_year}",
                tournament
            )
        except Exception as e:
            print(f"Error creating poster: {e}")
            poster_image = None
    else:
        print("No template images found in Templates folder")
    
    # Create event embed with new format
    embed = discord.Embed(
        title="Schedule",
        description=f"🗓️ {team_1_captain.display_name} VS {team_2_captain.display_name}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    # Tournament and Time Information
    # Create Discord timestamp for automatic timezone conversion
    timestamp = int(event_datetime.timestamp())
    embed.add_field(
        name="📋 Event Details", 
        value=f"**Tournament:** {tournament}\n"
              f"**UTC Time:** {time_info['utc_time']}\n"
              f"**Local Time:** <t:{timestamp}:F> (<t:{timestamp}:R>)\n"
              f"**Round:** Round {round}\n"
              f"**Channel:** {interaction.channel.mention}",
        inline=False
    )
    
    # Add spacing
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    
    # Captains Section
    captains_text = f"**Captains**\n"
    captains_text += f"▪ Team1 Captain: {team_1_captain.mention}\n"
    captains_text += f"▪ Team2 Captain: {team_2_captain.mention}"
    embed.add_field(name="👑 Team Captains", value=captains_text, inline=False)
    
    # Add spacing
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    
    # Staff Section
    staff_text = f"**Staffs**\n"
    staff_text += f"▪ Judge: *To be assigned*"
    embed.add_field(name="👨‍⚖️ Staff", value=staff_text, inline=False)
    
    # Add spacing
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    
    embed.add_field(name="👤 Created By", value=interaction.user.mention, inline=False)
    
    # Add poster image if available
    if poster_image:
        try:
            with open(poster_image, 'rb') as f:
                file = discord.File(f, filename="event_poster.png")
                embed.set_image(url="attachment://event_poster.png")
        except Exception as e:
            print(f"Error loading poster image: {e}")
    
    embed.set_footer(text="Event Management • ICF Tournament Bot")
    
    # Create Take Schedule button
    take_schedule_view = TakeScheduleButton(event_id, team_1_captain, team_2_captain, interaction.channel)
    
    # Send confirmation to user
    await interaction.followup.send("✅ Event created and posted to both channels! Reminder will ping captains 10 minutes before start.", ephemeral=True)
    
    # Post in Take-Schedule channel (with button)
    try:
        schedule_channel = interaction.guild.get_channel(CHANNEL_IDS["schedules"])
        if schedule_channel:
            judge_ping = f"<@&{ROLE_IDS['helpers_tournament']}> <@&{ROLE_IDS['organizers']}>"
            if poster_image:
                with open(poster_image, 'rb') as f:
                    file = discord.File(f, filename="event_poster.png")
                    schedule_message = await schedule_channel.send(content=judge_ping, embed=embed, file=file, view=take_schedule_view)
            else:
                schedule_message = await schedule_channel.send(content=judge_ping, embed=embed, view=take_schedule_view)
            
            # Store the message ID for later deletion
            scheduled_events[event_id]['schedule_message_id'] = schedule_message.id
            scheduled_events[event_id]['schedule_channel_id'] = schedule_channel.id
        else:
            await interaction.followup.send("⚠️ Could not find Take-Schedule channel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Could not post in Take-Schedule channel: {e}", ephemeral=True)
    
    # Post in the channel where command was used (without button)
    try:
        if poster_image:
            with open(poster_image, 'rb') as f:
                file = discord.File(f, filename="event_poster.png")
                await interaction.channel.send(embed=embed, file=file)
        else:
            await interaction.channel.send(embed=embed)

        # Schedule the 10-minute reminder
        await schedule_ten_minute_reminder(event_id, team_1_captain, team_2_captain, None, interaction.channel, event_datetime)
        
    except Exception as e:
        await interaction.followup.send(f"⚠️ Could not post in current channel: {e}", ephemeral=True)

@tree.command(name="event-result", description="Add event results (Organizers/Helpers Tournament only)")
@app_commands.describe(
    winner="Winner of the event",
    winner_score="Winner's score",
    loser="Loser of the event", 
    loser_score="Loser's score",
    tournament="Tournament name (e.g., The Zumwalt S2)",
    round="Round name (e.g., Semi-Final, Final, Quarter-Final)",
    remarks="Remarks about the match (e.g., ggwp, close match)",
    ss_1="Screenshot 1 (upload)",
    ss_2="Screenshot 2 (upload)",
    ss_3="Screenshot 3 (upload)",
    ss_4="Screenshot 4 (upload)",
    ss_5="Screenshot 5 (upload)",
    ss_6="Screenshot 6 (upload)",
    ss_7="Screenshot 7 (upload)",
    ss_8="Screenshot 8 (upload)",
    ss_9="Screenshot 9 (upload)",
    ss_10="Screenshot 10 (upload)",
    ss_11="Screenshot 11 (upload)"
)
async def event_result(
    interaction: discord.Interaction,
    winner: discord.Member,
    winner_score: int,
    loser: discord.Member,
    loser_score: int,
    tournament: str,
    round: str,
    remarks: str = "ggwp",
    ss_1: discord.Attachment = None,
    ss_2: discord.Attachment = None,
    ss_3: discord.Attachment = None,
    ss_4: discord.Attachment = None,
    ss_5: discord.Attachment = None,
    ss_6: discord.Attachment = None,
    ss_7: discord.Attachment = None,
    ss_8: discord.Attachment = None,
    ss_9: discord.Attachment = None,
    ss_10: discord.Attachment = None,
    ss_11: discord.Attachment = None
):
    """Adds results for an event"""
    
    # Defer the response immediately to avoid timeout issues
    await interaction.response.defer(ephemeral=True)
    
    # Check permissions
    if not has_event_result_permission(interaction):
        await interaction.followup.send("❌ You need **Organizers** or **Helpers Tournament** role to post event results.", ephemeral=True)
        return

    # Validate scores
    if winner_score < 0 or loser_score < 0:
        await interaction.followup.send("❌ Scores cannot be negative", ephemeral=True)
        return
            
    # Create results embed matching the exact template format
    embed = discord.Embed(
        title="Results",
        description=f"🗓️ {winner.display_name} Vs {loser.display_name}\n"
                   f"**Tournament:** {tournament}\n"
                   f"**Round:** {round}",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    
    # Captains Section
    captains_text = f"**Captains**\n"
    captains_text += f"▪ Team1 Captain: {winner.mention} `@{winner.name}`\n"
    captains_text += f"▪ Team2 Captain: {loser.mention} `@{loser.name}`"
    embed.add_field(name="", value=captains_text, inline=False)
    
    # Results Section
    results_text = f"**Results**\n"
    results_text += f"🏆 {winner.display_name} ({winner_score}) Vs ({loser_score}) {loser.display_name} 💀"
    embed.add_field(name="", value=results_text, inline=False)
    
    # Staff Section
    staff_text = f"👨‍⚖️ **Staffs**\n"
    staff_text += f"▪ Judge: {interaction.user.mention} `@{interaction.user.name}`"
    embed.add_field(name="", value=staff_text, inline=False)
    
    # Remarks Section
    embed.add_field(name="📝 Remarks", value=remarks, inline=False)
    
    # Handle screenshots - collect them and send as files (no image embeds)
    screenshots = [ss_1, ss_2, ss_3, ss_4, ss_5, ss_6, ss_7, ss_8, ss_9, ss_10, ss_11]
    files_to_send = []
    screenshot_names = []
    
    for i, screenshot in enumerate(screenshots, 1):
        if screenshot:
            # Create a file object for each screenshot
            try:
                file_data = await screenshot.read()
                file_obj = discord.File(
                    fp=io.BytesIO(file_data),
                    filename=f"SS-{i}_{screenshot.filename}"
                )
                files_to_send.append(file_obj)
                screenshot_names.append(f"SS-{i}")
            except Exception as e:
                print(f"Error processing screenshot {i}: {e}")
    
    # Add screenshot section if any screenshots were provided
    if screenshot_names:
        screenshot_text = f"**Screenshots of Result ({len(screenshot_names)} images)**\n"
        screenshot_text += f"📷 {' • '.join(screenshot_names)}"
        embed.add_field(name="", value=screenshot_text, inline=False)
    
    embed.set_footer(text="Event Results • ICF Tournament Bot")
    
    # Send confirmation to user
    await interaction.followup.send("✅ Event results posted to Results channel and Staff Attendance logged!", ephemeral=True)
    
    # Post in Results channel with screenshots as attachments
    try:
        results_channel = interaction.guild.get_channel(CHANNEL_IDS["match_results"])
        if results_channel:
            if files_to_send:
                # Send as attachments + single embed so Discord shows gallery above embed
                await results_channel.send(embed=embed, files=files_to_send)
            else:
                await results_channel.send(embed=embed)
        else:
            await interaction.followup.send("⚠️ Could not find Results channel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Could not post in Results channel: {e}", ephemeral=True)

    # Winner-only summary removed per request

    # Post staff attendance in match_reports channel
    try:
        reports_channel = interaction.guild.get_channel(CHANNEL_IDS["match_reports"])
        if reports_channel:
            attendance_text = f"🏅 {winner.display_name} Vs {loser.display_name}\n"
            attendance_text += f"**Round :** {round}\n\n"
            attendance_text += f"**Results**\n"
            attendance_text += f"🏆 {winner.display_name} ({winner_score}) Vs ({loser_score}) {loser.display_name} 💀\n\n"
            attendance_text += f"**Staffs**\n"
            attendance_text += f"• Judge: {interaction.user.mention} `@{interaction.user.name}`"

            await reports_channel.send(attendance_text)
        else:
            print("⚠️ Could not find match reports channel.")
    except Exception as e:
        print(f"⚠️ Could not post in match reports channel: {e}")

@tree.command(name="time", description="Get a random match time from fixed 30-min slots (12:00-17:00 UTC)")
async def time(interaction: discord.Interaction):
    """Pick a random time from 30-minute slots between 12:00 and 17:00 UTC and show all slots."""
    
    import random
    
    # Build fixed 30-minute slots from 12:00 to 17:00 (inclusive), excluding 17:30
    slots = [
        f"{hour:02d}:{minute:02d} UTC"
        for hour in range(12, 18)
        for minute in (0, 30)
        if not (hour == 17 and minute == 30)
    ]
    
    chosen_time = random.choice(slots)
    
    embed = discord.Embed(
        title="⏰ Match Time (30‑min slots)",
        description=f"**Your random match time:** {chosen_time}",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
                    )
                                       
    embed.add_field(
        name="🕒 Range",
        value="From 12:00 to 17:00 UTC (every 30 minutes)",
        inline=False
    )
                    
    embed.set_footer(text="Match Time Generator • ICF Tournament Bot")
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="choose", description="Randomly choose from a list of options or maps")
@app_commands.describe(
    options="List of options separated by commas, or a number (1-20) for maps"
)
async def choose(interaction: discord.Interaction, options: str):
    """Randomly selects one option from a comma-separated list or predefined maps"""
    
    import random
    
    # Predefined map list
    maps = [
        "New Storm (2024)",
        "Arid Frontier", 
        "Islands of Iceland",
        "Unexplored Rocks",
        "Arctic",
        "Lost City",
        "Polar Frontier",
        "Hidden Dragon",
        "Monstrous Maelstrom",
        "Two Samurai",
        "Stone Peaks",
        "Viking Bay",
        "Greenlands",
        "Old Storm",
        "Rising Fortress "
    ]
    
    # Check if input is a number (for map selection)
    if options.strip().isdigit():
        number = int(options.strip())
        if 1 <= number <= len(maps):
            # Randomly select 'number' of maps
            selected_maps = random.sample(maps, number)
            
            embed = discord.Embed(
                title="🗺️ Random Map Selection - ICF Tournament Bot",
                description=f"**Randomly selected {number} map(s):**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            
            # Add selected maps as a field
            selected_maps_text = "\n".join([f"• {map_name}" for map_name in selected_maps])
            embed.add_field(
                name=f"🎯 Selected Maps ({number})",
                value=selected_maps_text,
                inline=False
            )
            
            embed.set_footer(text="Random Map Selection • ICF Tournament Bot")
            await interaction.response.send_message(embed=embed)
            return
        else:
            await interaction.response.send_message(f"❌ Please enter a number between 1 and {len(maps)} for map selection.", ephemeral=True)
            return
    
    # Handle comma-separated options (original functionality)
    option_list = [option.strip() for option in options.split(',') if option.strip()]
    
    # Validate input
    if len(option_list) < 2:
        await interaction.response.send_message("❌ Please provide at least 2 options separated by commas, or enter a number (1-14) for maps.", ephemeral=True)
        return
    
    if len(option_list) > 20:
        await interaction.response.send_message("❌ Too many options! Please provide 20 or fewer options.", ephemeral=True)
        return
    
    # Randomly select one option
    chosen_option = random.choice(option_list)
    
    # Create embed
    embed = discord.Embed(
        title="🎲 Random Choice",
        description=f"**Selected:** {chosen_option}",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow()
    )
    
    # Add all options as a field
    options_text = "\n".join([f"• {option}" for option in option_list])
    embed.add_field(
        name=f"📋 Available Options ({len(option_list)})",
        value=options_text,
        inline=False
    )
    
    embed.set_footer(text="Random Choice Generator • ICF Tournament Bot")
    
    await interaction.response.send_message(embed=embed)


@tree.command(name="general_tie_breaker", description="To break a tie between two teams using the highest total score")
@app_commands.describe(
    tm1_name="Name of the first team. By default, it is Alpha",
    tm1_pl1_score="Score of the first player of the first team",
    tm1_pl2_score="Score of the second player of the first team", 
    tm1_pl3_score="Score of the third player of the first team",
    tm1_pl4_score="Score of the fourth player of the first team",
    tm1_pl5_score="Score of the fifth player of the first team",
    tm2_name="Name of the second team. By default, it is Bravo",
    tm2_pl1_score="Score of the first player of the second team",
    tm2_pl2_score="Score of the second player of the second team",
    tm2_pl3_score="Score of the third player of the second team",
    tm2_pl4_score="Score of the fourth player of the second team",
    tm2_pl5_score="Score of the fifth player of the second team"
)
async def general_tie_breaker(
    interaction: discord.Interaction,
    tm1_pl1_score: int,
    tm1_pl2_score: int,
    tm1_pl3_score: int,
    tm1_pl4_score: int,
    tm1_pl5_score: int,
    tm2_pl1_score: int,
    tm2_pl2_score: int,
    tm2_pl3_score: int,
    tm2_pl4_score: int,
    tm2_pl5_score: int,
    tm1_name: str = "Alpha",
    tm2_name: str = "Bravo"
):
    """Break a tie between two teams using the highest total score"""
    
    # Check permissions - only organizers and helpers can use this command
    if not has_event_create_permission(interaction):
        await interaction.response.send_message("❌ You need **Organizers** or **Helpers Tournament** role to use tie breaker.", ephemeral=True)
        return
    
    # Calculate team totals
    tm1_total = tm1_pl1_score + tm1_pl2_score + tm1_pl3_score + tm1_pl4_score + tm1_pl5_score
    tm2_total = tm2_pl1_score + tm2_pl2_score + tm2_pl3_score + tm2_pl4_score + tm2_pl5_score
    
    # Determine winner
    if tm1_total > tm2_total:
        winner = tm1_name
        winner_total = tm1_total
        loser = tm2_name
        loser_total = tm2_total
        color = discord.Color.green()
    elif tm2_total > tm1_total:
        winner = tm2_name
        winner_total = tm2_total
        loser = tm1_name
        loser_total = tm1_total
        color = discord.Color.green()
    else:
        # Still tied
        winner = "TIE"
        winner_total = tm1_total
        loser = ""
        loser_total = tm2_total
        color = discord.Color.orange()
    
    # Create result embed
    embed = discord.Embed(
        title="🏆 Tie Breaker Results",
        description="Results based on highest total team score",
        color=color,
        timestamp=discord.utils.utcnow()
    )
    
    # Team 1 scores
    embed.add_field(
        name=f"🔵 {tm1_name} Team",
        value=f"Player 1: `{tm1_pl1_score}`\n"
              f"Player 2: `{tm1_pl2_score}`\n"
              f"Player 3: `{tm1_pl3_score}`\n"
              f"Player 4: `{tm1_pl4_score}`\n"
              f"Player 5: `{tm1_pl5_score}`\n"
              f"**Total: {tm1_total}**",
        inline=True
    )
    
    # Team 2 scores
    embed.add_field(
        name=f"🔴 {tm2_name} Team",
        value=f"Player 1: `{tm2_pl1_score}`\n"
              f"Player 2: `{tm2_pl2_score}`\n"
              f"Player 3: `{tm2_pl3_score}`\n"
              f"Player 4: `{tm2_pl4_score}`\n"
              f"Player 5: `{tm2_pl5_score}`\n"
              f"**Total: {tm2_total}**",
        inline=True
    )
    
    # Add spacing
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    
    # Result
    if winner == "TIE":
        embed.add_field(
            name="🤝 Final Result",
            value=f"**STILL TIED!**\n"
                  f"Both teams scored {tm1_total} points\n"
                  f"Additional tie-breaking method needed",
            inline=False
        )
    else:
        embed.add_field(
            name="🏆 Winner",
            value=f"**{winner}** wins the tie breaker!\n"
                  f"**{winner}**: {winner_total} points\n"
                  f"**{loser}**: {loser_total} points\n"
                  f"Difference: {abs(winner_total - loser_total)} points",
            inline=False
        )
    
    embed.set_footer(text=f"Tie Breaker • Calculated by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="event-delete", description="Delete a scheduled event (Organizers/Helpers Tournament)")
async def event_delete(interaction: discord.Interaction):
    # Check permissions - Organizers and Helpers Tournament can delete events
    organizers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["organizers"])
    helpers_role = discord.utils.get(interaction.user.roles, id=ROLE_IDS["helpers_tournament"])
    
    if not (organizers_role or helpers_role):
        await interaction.response.send_message("❌ You need **Organizers** or **Helpers Tournament** role to delete events.", ephemeral=True)
        return
    
    try:
        # Check if there are any scheduled events
        if not scheduled_events:
            await interaction.response.send_message(f"❌ No scheduled events found to delete.\n\n**Debug Info:**\n• Scheduled events count: {len(scheduled_events)}\n• Events in memory: {list(scheduled_events.keys()) if scheduled_events else 'None'}", ephemeral=True)
            return
        
        # Create dropdown with event names
        class EventDeleteView(View):
            def __init__(self):
                super().__init__(timeout=60)
                
            @discord.ui.select(
                placeholder="Select an event to delete...",
                options=[
                    discord.SelectOption(
                        label=f"{event_data.get('team1_captain').display_name if event_data.get('team1_captain') else 'Unknown'} VS {event_data.get('team2_captain').display_name if event_data.get('team2_captain') else 'Unknown'}",
                        description=f"{event_data.get('round', 'Unknown Round')} - {event_data.get('date_str', 'No date')} at {event_data.get('time_str', 'No time')}",
                        value=event_id
                    )
                    for event_id, event_data in list(scheduled_events.items())[:25]  # Discord limit of 25 options
                ]
            )
            async def select_event(self, select_interaction: discord.Interaction, select: discord.ui.Select):
                selected_event_id = select.values[0]
                
                # Get event details for confirmation
                event_data = scheduled_events[selected_event_id]
                
                # Cancel any scheduled reminders
                if selected_event_id in reminder_tasks:
                    reminder_tasks[selected_event_id].cancel()
                    del reminder_tasks[selected_event_id]
                
                # Remove judge assignment if exists
                if 'judge' in event_data and event_data['judge']:
                    judge_id = event_data['judge'].id
                    remove_judge_assignment(judge_id, selected_event_id)
                
                # Delete the original schedule message if it exists
                deleted_message = False
                if 'schedule_message_id' in event_data and 'schedule_channel_id' in event_data:
                    try:
                        schedule_channel = select_interaction.guild.get_channel(event_data['schedule_channel_id'])
                        if schedule_channel:
                            schedule_message = await schedule_channel.fetch_message(event_data['schedule_message_id'])
                            await schedule_message.delete()
                            deleted_message = True
                    except discord.NotFound:
                        pass  # Message already deleted
                    except Exception as e:
                        print(f"Error deleting schedule message: {e}")
                
                # Clean up any temporary poster files
                if 'poster_path' in event_data:
                    try:
                        import os
                        if os.path.exists(event_data['poster_path']):
                            os.remove(event_data['poster_path'])
                    except Exception as e:
                        print(f"Error deleting poster file: {e}")
                
                # Remove from scheduled events
                del scheduled_events[selected_event_id]
                
                # Save events to file
                save_scheduled_events()
                
                # Create confirmation embed
                embed = discord.Embed(
                    title="🗑️ Event Deleted",
                    description=f"Event has been successfully deleted.",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                
                embed.add_field(
                    name="📋 Deleted Event Details",
                    value=f"**Title:** {event_data.get('title', 'N/A')}\n**Round:** {event_data.get('round', 'N/A')}\n**Time:** {event_data.get('time_str', 'N/A')}\n**Date:** {event_data.get('date_str', 'N/A')}",
                    inline=False
                )
                
                # Build actions completed list
                actions_completed = [
                    "• Event removed from schedule",
                    "• Reminder cancelled",
                    "• Judge assignment cleared"
                ]
                
                if deleted_message:
                    actions_completed.append("• Original schedule message deleted")
                
                if 'poster_path' in event_data:
                    actions_completed.append("• Temporary poster file cleaned up")
                
                embed.add_field(
                    name="✅ Actions Completed",
                    value="\n".join(actions_completed),
                    inline=False
                )
                
                embed.set_footer(text="Event Management • ICF Tournament Bot")
                
                await select_interaction.response.edit_message(embed=embed, view=None)
        
        # Create initial embed
        embed = discord.Embed(
            title="🗑️ Delete Event",
            description="Select an event from the dropdown below to delete it.",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📋 Available Events",
            value=f"Found {len(scheduled_events)} scheduled event(s)",
            inline=False
        )
        
        embed.set_footer(text="Event Management • ICF Tournament Bot")
        
        view = EventDeleteView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)


@tree.command(name="exchange_judge", description="Exchange an old judge for a new judge for event(s) in this channel")
@app_commands.describe(
    old_judge="The current judge to replace",
    new_judge="The new judge to assign"
)
async def exchange_judge(
    interaction: discord.Interaction,
    old_judge: discord.Member,
    new_judge: discord.Member
):
    # Only Head Helper or Helper Team can exchange judges
    if not has_event_create_permission(interaction):
        await interaction.response.send_message("❌ You need Head Organizer, Head Helper or Helper Team role to exchange judges.", ephemeral=True)
        return

    # Validate roles of old/new helpers (replace Judge role with Helpers Tournament role)
    helpers_role = discord.utils.get(interaction.guild.roles, id=ROLE_IDS["helpers_tournament"]) if interaction.guild else None
    if helpers_role:
        if helpers_role not in old_judge.roles:
            await interaction.response.send_message("❌ The current assignee does not have the Helpers Tournament role.", ephemeral=True)
            return
        if helpers_role not in new_judge.roles:
            await interaction.response.send_message("❌ The new assignee must have the Helpers Tournament role.", ephemeral=True)
            return

    # Determine target events in the current channel
    target_event_ids = []
    current_channel_id = interaction.channel.id if interaction.channel else None
    for ev_id, data in scheduled_events.items():
        if data.get('channel_id') == current_channel_id and data.get('judge') and getattr(data.get('judge'), 'id', None) == old_judge.id:
            target_event_ids.append(ev_id)

    if not target_event_ids:
        await interaction.response.send_message("⚠️ No events in this channel are assigned to the old judge.", ephemeral=True)
        return

    # Perform exchange
    updated_count = 0
    for ev_id in target_event_ids:
        data = scheduled_events.get(ev_id)
        if not data:
            continue
        # Update event's judge
        data['judge'] = new_judge

        # Update judge_assignments mapping
        try:
            remove_judge_assignment(old_judge.id, ev_id)
        except Exception:
            pass
        add_judge_assignment(new_judge.id, ev_id)

        # Judge assigned successfully (reminder system removed)

        # Handle channel permissions and send notification to the event channel
        try:
            if interaction.guild and data.get('channel_id'):
                channel = interaction.guild.get_channel(data['channel_id'])
                if channel:
                    # Remove old judge from channel
                    await channel.set_permissions(old_judge, overwrite=None)
                    
                    # Add new judge to channel
                    await channel.set_permissions(
                        new_judge, 
                        read_messages=True, 
                        send_messages=True, 
                        view_channel=True,
                        embed_links=True,
                        attach_files=True,
                        read_message_history=True
                    )
                    
                    embed = discord.Embed(
                        title="🔁 Judge Exchanged",
                        description=(
                            f"**Old judge:** {old_judge.mention} `@{old_judge.name}`\n"
                            f"**New judge:** {new_judge.mention} `@{new_judge.name}`"
                        ),
                        color=discord.Color.purple(),
                        timestamp=discord.utils.utcnow()
                    )
                    channel_mention = channel.mention if channel else ""
                    embed.add_field(
                        name="📋 Event",
                        value=f"{channel_mention} • Time: {data.get('time_str', '')} • {data.get('round', '')}",
                        inline=False
                    )
                    embed.add_field(
                        name="🔐 Channel Access",
                        value=f"❌ **{old_judge.display_name}** removed from channel\n✅ **{new_judge.display_name}** added to channel",
                        inline=False
                    )
                    await channel.send(embed=embed)
        except discord.Forbidden:
            print(f"Error: Bot doesn't have permission to manage channel permissions for {ev_id}")
        except Exception as e:
            print(f"Failed to send judge exchange notification for {ev_id}: {e}")

        updated_count += 1

    await interaction.response.send_message(f"✅ Judge exchanged for {updated_count} event(s) in {interaction.channel.mention}.", ephemeral=True)


# Ticket Management Commands - Removed as requested


if __name__ == "__main__":
    # Get Discord token from environment
    token = os.environ.get("DISCORD_TOKEN")
    
    # Fallback method if direct get doesn't work
    if not token:
        for key, value in os.environ.items():
            if 'DISCORD' in key and 'TOKEN' in key:
                token = value
                break
    
    if not token:
        print("❌ Discord token not found in environment variables.")
        print("Please set your Discord bot token in the DISCORD_TOKEN environment variable.")
        print("You can also create a .env file with: DISCORD_TOKEN=your_token_here")
        exit(1)
    
    try:
        print("🚀 Starting Discord bot...")
        print("📡 Connecting to Discord...")
        # Ensure tree commands are fully registered before running
        bot.run(token, log_handler=None)  # Disable default logging to reduce startup time
    except discord.LoginFailure:
        print("❌ Invalid Discord token. Please check your bot token.")
        exit(1)
    except discord.HTTPException as e:
        print(f"❌ HTTP error connecting to Discord: {e}")
        exit(1)
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        exit(1)

@tree.command(name="general_tie_breaker", description="To break a tie between two teams using the highest total score")
@app_commands.describe(
    tm1_name="Name of the first team. By default, it is Alpha",
    tm1_pl1_score="Score of the first player of the first team",
    tm1_pl2_score="Score of the second player of the first team", 
    tm1_pl3_score="Score of the third player of the first team",
    tm1_pl4_score="Score of the fourth player of the first team",
    tm1_pl5_score="Score of the fifth player of the first team",
    tm2_name="Name of the second team. By default, it is Bravo",
    tm2_pl1_score="Score of the first player of the second team",
    tm2_pl2_score="Score of the second player of the second team",
    tm2_pl3_score="Score of the third player of the second team",
    tm2_pl4_score="Score of the fourth player of the second team",
    tm2_pl5_score="Score of the fifth player of the second team"
)
async def general_tie_breaker(
    interaction: discord.Interaction,
    tm1_pl1_score: int,
    tm1_pl2_score: int,
    tm1_pl3_score: int,
    tm1_pl4_score: int,
    tm1_pl5_score: int,
    tm2_pl1_score: int,
    tm2_pl2_score: int,
    tm2_pl3_score: int,
    tm2_pl4_score: int,
    tm2_pl5_score: int,
    tm1_name: str = "Alpha",
    tm2_name: str = "Bravo"
):
    """Break a tie between two teams using the highest total score"""
    
    # Check permissions - only organizers and helpers can use this command
    if not has_event_create_permission(interaction):
        await interaction.response.send_message("❌ You need **Organizers** or **Helpers Tournament** role to use tie breaker.", ephemeral=True)
        return
    
    # Calculate team totals
    tm1_total = tm1_pl1_score + tm1_pl2_score + tm1_pl3_score + tm1_pl4_score + tm1_pl5_score
    tm2_total = tm2_pl1_score + tm2_pl2_score + tm2_pl3_score + tm2_pl4_score + tm2_pl5_score
    
    # Determine winner
    if tm1_total > tm2_total:
        winner = tm1_name
        winner_total = tm1_total
        loser = tm2_name
        loser_total = tm2_total
        color = discord.Color.green()
    elif tm2_total > tm1_total:
        winner = tm2_name
        winner_total = tm2_total
        loser = tm1_name
        loser_total = tm1_total
        color = discord.Color.green()
    else:
        # Still tied
        winner = "TIE"
        winner_total = tm1_total
        loser = ""
        loser_total = tm2_total
        color = discord.Color.orange()
    
    # Create result embed
    embed = discord.Embed(
        title="🏆 Tie Breaker Results",
        description="Results based on highest total team score",
        color=color,
        timestamp=discord.utils.utcnow()
    )
    
    # Team 1 scores
    embed.add_field(
        name=f"🔵 {tm1_name} Team",
        value=f"Player 1: `{tm1_pl1_score}`\n"
              f"Player 2: `{tm1_pl2_score}`\n"
              f"Player 3: `{tm1_pl3_score}`\n"
              f"Player 4: `{tm1_pl4_score}`\n"
              f"Player 5: `{tm1_pl5_score}`\n"
              f"**Total: {tm1_total}**",
        inline=True
    )
    
    # Team 2 scores
    embed.add_field(
        name=f"🔴 {tm2_name} Team",
        value=f"Player 1: `{tm2_pl1_score}`\n"
              f"Player 2: `{tm2_pl2_score}`\n"
              f"Player 3: `{tm2_pl3_score}`\n"
              f"Player 4: `{tm2_pl4_score}`\n"
              f"Player 5: `{tm2_pl5_score}`\n"
              f"**Total: {tm2_total}**",
        inline=True
    )
    
    # Add spacing
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    
    # Result
    if winner == "TIE":
        embed.add_field(
            name="🤝 Final Result",
            value=f"**STILL TIED!**\n"
                  f"Both teams scored {tm1_total} points\n"
                  f"Additional tie-breaking method needed",
            inline=False
        )
    else:
        embed.add_field(
            name="🏆 Winner",
            value=f"**{winner}** wins the tie breaker!\n"
                  f"**{winner}**: {winner_total} points\n"
                  f"**{loser}**: {loser_total} points\n"
                  f"Difference: {abs(winner_total - loser_total)} points",
            inline=False
        )
    
    embed.set_footer(text=f"Tie Breaker • Calculated by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)
